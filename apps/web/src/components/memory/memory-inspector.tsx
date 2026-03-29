"use client";

import type { ReactNode } from "react";
import { X } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getMemoryTypeLabel, getMemoryTypeMeta } from "@/lib/memory-constants";
import type {
  MemoryGraphEdge,
  MemoryGraphNode,
  MemoryLearningNode,
  MemorySemanticStatus,
} from "@/lib/types";
import { cn, formatDateTime, formatRelativeTime, truncateText } from "@/lib/utils";
import { SyntaxHighlight } from "../shared/syntax-highlight";

type MemoryNode = MemoryGraphNode | MemoryLearningNode;

interface MemoryInspectorProps {
  node: MemoryNode | null;
  relatedNodes: MemoryNode[];
  relatedEdges: MemoryGraphEdge[];
  semanticStatus: MemorySemanticStatus;
  className?: string;
  onClose?: () => void;
}

function isMemoryNode(node: MemoryNode): node is MemoryGraphNode {
  return node.kind === "memory";
}

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-[var(--border-subtle)] pt-5 first:border-t-0 first:pt-0">
      <div className="mb-3">
        <p className="eyebrow">{title}</p>
      </div>
      {children}
    </section>
  );
}

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="grid gap-1.5 py-3 first:pt-0 last:pb-0 sm:grid-cols-[112px_minmax(0,1fr)] sm:gap-3 sm:items-start">
      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
        {label}
      </span>
      <span
        className={cn(
          "text-sm leading-6 text-[var(--text-secondary)] [overflow-wrap:anywhere]",
          mono && "font-mono text-[12px]"
        )}
      >
        {value}
      </span>
    </div>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
        {label}
      </p>
      <p className="mt-2 text-[0.98rem] font-semibold leading-6 tracking-[-0.03em] text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {value}
      </p>
    </div>
  );
}

function EmptyState({
  className,
  onClose,
}: {
  className?: string;
  onClose?: () => void;
}) {
  const { t } = useAppI18n();
  return (
      <div
        className={cn(
          "glass-card h-full border-[var(--border-strong)] bg-[var(--surface-elevated-soft)] p-5 shadow-[0_18px_30px_rgba(0,0,0,0.16)] sm:p-6",
          className
        )}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[1.4rem] font-semibold leading-[1.08] tracking-[-0.055em] text-[var(--text-primary)] sm:text-[1.5rem]">
            {t("memory.inspector.selectPoint")}
          </h2>
        </div>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="button-shell button-shell--secondary button-shell--icon h-10 w-10 shrink-0 text-[var(--text-secondary)]"
            aria-label={t("memory.inspector.close")}
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function MemoryInspector({
  node,
  relatedNodes,
  relatedEdges,
  semanticStatus,
  className,
  onClose,
}: MemoryInspectorProps) {
  const { t } = useAppI18n();
  if (!node) {
    return <EmptyState className={className} onClose={onClose} />;
  }

  if (isMemoryNode(node)) {
    const meta = getMemoryTypeMeta(node.memory_type);

    return (
      <div
        className={cn(
          "glass-card h-full overflow-auto border-[var(--border-strong)] bg-[var(--surface-elevated-soft)] p-5 shadow-[0_18px_30px_rgba(0,0,0,0.16)] sm:p-6",
          className
        )}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="inline-flex min-h-8 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-3 text-[11px] font-semibold uppercase tracking-[0.12em]"
                style={{ color: meta.color }}
              >
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: meta.color }} />
                {getMemoryTypeLabel(node.memory_type, t)}
              </span>
              <span className="inline-flex min-h-8 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                {node.is_active ? t("memory.inspector.active") : t("memory.inspector.inactive")}
              </span>
            </div>
            <h2 className="mt-4 text-[1.35rem] font-semibold leading-[1.08] tracking-[-0.055em] text-[var(--text-primary)] sm:text-[1.55rem] [overflow-wrap:anywhere]">
              {node.title}
            </h2>
            <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
              {node.content}
            </p>
          </div>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="button-shell button-shell--secondary button-shell--icon h-10 w-10 shrink-0 text-[var(--text-secondary)]"
              aria-label={t("memory.inspector.close")}
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          <Metric label={t("memory.inspector.importance")} value={`${Math.round(node.importance * 100)}%`} />
          <Metric label={t("memory.inspector.accesses")} value={`${node.access_count}`} />
          <Metric
            label={t("memory.inspector.lastUsed")}
            value={node.last_accessed ? formatRelativeTime(node.last_accessed) : t("memory.inspector.notAccessedYet")}
          />
          <Metric
            label={t("memory.inspector.createdAt")}
            value={node.created_at ? formatDateTime(node.created_at) : t("memory.inspector.noDate")}
          />
        </div>

        <div className="mt-6 space-y-5">
          <Section title={t("memory.inspector.origin")}>
            <div className="divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4">
              <InfoRow
                label={t("common.session")}
                value={node.session_id ? truncateText(node.session_id, 42) : t("memory.inspector.noLinkedSession")}
                mono
              />
              <InfoRow
                label={t("common.query")}
                value={node.source_query_text || node.source_query_preview || t("memory.inspector.unavailable")}
              />
            </div>
          </Section>

          <Section title={t("memory.inspector.relatedConnections")}>
            {relatedNodes.length > 0 ? (
              <div className="space-y-2.5">
                {relatedNodes.slice(0, 6).map((related) => {
                  const relation = relatedEdges.find(
                    (edge) =>
                      (edge.source === node.id && edge.target === related.id) ||
                      (edge.target === node.id && edge.source === related.id)
                  );

                  return (
                    <div
                      key={related.id}
                      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                            {related.title}
                          </p>
                          <p className="mt-1 text-xs leading-6 text-[var(--text-tertiary)]">
                            {related.kind === "memory"
                              ? getMemoryTypeLabel(related.memory_type, t)
                              : t("memory.inspector.syntheticLearning")}
                          </p>
                        </div>
                        {relation ? (
                          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                            {relation.type === "semantic"
                              ? t("memory.inspector.semantic")
                              : relation.type === "session"
                                ? t("common.session")
                                : relation.type === "source"
                                  ? t("memory.inspector.source")
                                  : t("memory.inspector.learning")}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm leading-7 text-[var(--text-tertiary)]">
                {t("memory.inspector.noVisibleConnections")}
              </p>
            )}
          </Section>

          {Object.keys(node.metadata).length > 0 ? (
            <Section title={t("memory.inspector.metadata")}>
              <SyntaxHighlight lang="json" className="p-4 text-[12px]">
                {JSON.stringify(node.metadata, null, 2)}
              </SyntaxHighlight>
            </Section>
          ) : null}
        </div>
      </div>
    );
  }

  const dominantMeta = getMemoryTypeMeta(node.dominant_type);

  return (
      <div
        className={cn(
          "glass-card h-full overflow-auto border-[var(--border-strong)] bg-[var(--surface-elevated-soft)] p-5 shadow-[0_18px_30px_rgba(0,0,0,0.16)] sm:p-6",
          className
        )}
      >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="inline-flex min-h-8 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-3 text-[11px] font-semibold uppercase tracking-[0.12em]"
              style={{ color: dominantMeta.color }}
            >
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: dominantMeta.color }}
              />
              {t("memory.inspector.learningBadge")}
            </span>
            <span className="inline-flex min-h-8 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
              {t("memory.inspector.memoriesCount", { count: node.member_count })}
            </span>
          </div>
          <h2 className="mt-4 text-[1.35rem] font-semibold leading-[1.08] tracking-[-0.055em] text-[var(--text-primary)] sm:text-[1.55rem] [overflow-wrap:anywhere]">
            {node.title}
          </h2>
          <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
            {node.summary}
          </p>
        </div>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="button-shell button-shell--secondary button-shell--icon h-10 w-10 shrink-0 text-[var(--text-secondary)]"
            aria-label={t("memory.inspector.close")}
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <Metric label={t("memory.inspector.dominantType")} value={getMemoryTypeLabel(node.dominant_type, t)} />
        <Metric label={t("memory.inspector.intensity")} value={`${Math.round(node.importance * 100)}%`} />
        <Metric
          label={t("memory.inspector.semanticStrength")}
          value={
            node.semantic_strength != null
              ? `${Math.round(node.semantic_strength * 100)}%`
              : semanticStatus === "available"
                ? t("memory.inspector.noStrongAffinity")
                : t("memory.inspector.contextualFallback")
          }
        />
        <Metric label={t("memory.inspector.sessions")} value={`${node.session_ids.length}`} />
      </div>

      <div className="mt-6 space-y-5">
        <Section title={t("memory.inspector.relatedMemories")}>
          {relatedNodes.length > 0 ? (
            <div className="space-y-2.5">
              {relatedNodes.slice(0, 8).map((related) => {
                const relatedMemory = related.kind === "memory" ? related : null;
                const relatedMeta = relatedMemory
                  ? getMemoryTypeMeta(relatedMemory.memory_type)
                  : dominantMeta;

                return (
                  <div
                    key={related.id}
                    className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: relatedMeta.color }}
                      />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere]">
                          {related.title}
                        </p>
                        <p className="mt-1 text-xs leading-6 text-[var(--text-tertiary)]">
                          {related.kind === "memory"
                            ? `${getMemoryTypeLabel(relatedMemory!.memory_type, t)} • ${Math.round(related.importance * 100)}%`
                            : truncateText(related.title, 60)}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            ) : (
              <p className="text-sm leading-7 text-[var(--text-tertiary)]">
                {t("memory.inspector.noRelatedMemories")}
              </p>
            )}
        </Section>
      </div>
    </div>
  );
}
