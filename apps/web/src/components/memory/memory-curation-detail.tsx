"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowUpRight, DatabaseZap, SearchX } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getBotLabel } from "@/lib/bot-constants";
import { getMemoryTypeLabel, getMemoryTypeMeta } from "@/lib/memory-constants";
import type {
  MemoryClusterReviewDetail,
  MemoryReviewDetail,
  MemoryReviewHistoryEntry,
  MemoryReviewItem,
  MemoryReviewStatus,
} from "@/lib/types";
import { cn, formatDateTime, formatRelativeTime } from "@/lib/utils";
import { MemoryClusterDetail } from "./memory-cluster-detail";
import { MemoryCurationActions } from "./memory-curation-actions";

function getStatusLabel(
  status: MemoryReviewStatus,
  t: (key: string, options?: Record<string, unknown>) => string
) {
  return t(`memory.curation.status.${status}`, { defaultValue: status });
}

function getStatusColor(status: MemoryReviewStatus) {
  switch (status) {
    case "approved":
      return "var(--tone-success-dot)";
    case "merged":
      return "var(--tone-retry-dot)";
    case "discarded":
      return "var(--tone-danger-dot)";
    case "expired":
      return "var(--tone-warning-dot)";
    case "archived":
      return "var(--tone-neutral-dot)";
    default:
      return "var(--tone-info-dot)";
  }
}

function DetailSection({
  eyebrow,
  children,
}: {
  eyebrow: string;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-[var(--border-subtle)] pt-5 first:border-t-0 first:pt-0">
      <p className="eyebrow">{eyebrow}</p>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function MemoryReferenceList({
  items,
  emptyLabel,
  onSelectMemory,
}: {
  items: MemoryReviewItem[];
  emptyLabel: string;
  onSelectMemory: (memoryId: number) => void;
}) {
  if (items.length === 0) {
    return <p className="text-sm leading-6 text-[var(--text-secondary)]">{emptyLabel}</p>;
  }

  return (
    <div className="divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.012)]">
      {items.map((item) => (
        <button
          key={item.memory_id}
          type="button"
          onClick={() => onSelectMemory(item.memory_id)}
          className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-[rgba(255,255,255,0.018)]"
        >
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-[var(--text-primary)]">
              {item.title}
            </p>
            <p className="mt-1 line-clamp-2 text-sm leading-6 text-[var(--text-secondary)]">
              {item.content}
            </p>
          </div>
          <span className="shrink-0 text-[11px] text-[var(--text-tertiary)]">
            {formatRelativeTime(item.last_accessed ?? item.created_at)}
          </span>
        </button>
      ))}
    </div>
  );
}

function ReviewHistory({
  history,
}: {
  history: MemoryReviewHistoryEntry[];
}) {
  const { t } = useAppI18n();
  if (history.length === 0) {
    return <p className="text-sm leading-6 text-[var(--text-secondary)]">{t("memory.curation.detail.noReviewRecorded")}</p>;
  }

  return (
    <div className="divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.012)]">
      {history.map((entry) => (
        <div key={entry.id} className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium text-[var(--text-primary)]">
              {t(`memory.curation.actions.${entry.action}`, {
                defaultValue: entry.action,
              })}
            </span>
            <span className="text-[var(--text-tertiary)]">•</span>
            <span className="text-[12px] text-[var(--text-tertiary)]">
              {formatDateTime(entry.created_at)}
            </span>
          </div>
          {entry.reason ? (
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{entry.reason}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function MemoryReviewDetailPane({
  detail,
  onAction,
  onSelectMemory,
  busy,
}: {
  detail: MemoryReviewDetail;
  onAction: (
    action: "approve" | "discard" | "expire" | "archive" | "restore" | "merge",
    options?: { duplicateOfMemoryId?: number | null }
  ) => void;
  onSelectMemory: (memoryId: number) => void;
  busy: boolean;
}) {
  const { t } = useAppI18n();
  const meta = getMemoryTypeMeta(detail.item.memory_type);
  const mapHref = `/memory?bot=${detail.item.bot_id}&search=${encodeURIComponent(detail.item.title)}`;
  const mergeOptions = detail.similar_memories.map((item) => ({
    value: item.memory_id,
    label: item.title,
  }));
  const statusColor = getStatusColor(detail.item.review_status);
  const createdAt = formatDateTime(detail.item.created_at);
  const lastAccessed = formatRelativeTime(detail.item.last_accessed ?? detail.item.created_at);
  const [mergeTargetId, setMergeTargetId] = useState<number | null>(
    mergeOptions[0]?.value ?? null
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0 border-b border-[var(--border-subtle)] bg-[rgba(12,12,12,0.9)] px-5 py-4">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--text-tertiary)]">
            <span
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1"
              style={{
                color: meta.color,
                backgroundColor: `color-mix(in srgb, ${meta.color} 10%, transparent)`,
              }}
            >
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: meta.color }} />
              {getMemoryTypeLabel(detail.item.memory_type, t)}
            </span>
            <span>{getBotLabel(detail.item.bot_id)}</span>
            {detail.item.session_id ? (
              <>
                <span>•</span>
                <span>{detail.item.session_id}</span>
              </>
            ) : null}
            <span>•</span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: statusColor }} />
              {getStatusLabel(detail.item.review_status, t)}
            </span>
          </div>

          <div className="flex flex-col gap-2">
            <h2 className="text-[1.25rem] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
              {detail.item.title}
            </h2>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-[var(--text-tertiary)]">
              <span>{t("memory.curation.detail.importanceMeta", { value: Math.round(detail.item.importance * 100) })}</span>
              <span>•</span>
              <span>{t("memory.curation.detail.accessesMeta", { value: detail.item.access_count })}</span>
              <span>•</span>
              <span>{t("memory.curation.detail.lastAccessedMeta", { value: lastAccessed })}</span>
              <span>•</span>
              <span>{t("memory.curation.detail.createdMeta", { value: createdAt })}</span>
            </div>
          </div>

          <MemoryCurationActions
            kind="memory"
            busy={busy}
            canMerge={mergeOptions.length > 0}
            mergeTargetOptions={mergeOptions}
            mergeTargetId={mergeTargetId}
            onMergeTargetChange={setMergeTargetId}
            className="pt-1"
            onAction={(action) =>
              onAction(action, {
                duplicateOfMemoryId: action === "merge" ? mergeTargetId : null,
              })
            }
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5" style={{ maxHeight: 'calc(100dvh - var(--shell-topbar-height) - 24rem)' }}>
        <div className="space-y-5">
          <DetailSection eyebrow={t("memory.curation.detail.content")}>
            <p className="text-sm leading-7 text-[var(--text-secondary)]">{detail.item.content}</p>
          </DetailSection>

          <DetailSection eyebrow={t("memory.curation.detail.sourceAndContext")}>
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <div>
                <p className="text-[12px] font-medium uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                  {t("memory.curation.detail.sourceQuery")}
                </p>
                <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                  {detail.source_query_text ?? t("memory.curation.detail.noSourceQuery")}
                </p>
              </div>

              <dl className="grid gap-3 sm:grid-cols-2">
                <div>
                  <dt className="text-[12px] uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                    {t("common.session")}
                  </dt>
                  <dd className="mt-1 text-sm text-[var(--text-primary)]">
                    {detail.session_name ?? detail.item.session_id ?? t("memory.curation.detail.sessionFallback")}
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                    {t("memory.curation.detail.cluster")}
                  </dt>
                  <dd className="mt-1 text-sm text-[var(--text-primary)]">
                    {detail.cluster?.member_count
                      ? t("memory.curation.detail.memoriesConnected", { count: detail.cluster.member_count })
                      : t("memory.curation.detail.noGrouping")}
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                    {t("memory.curation.detail.editorialStatus")}
                  </dt>
                  <dd className="mt-1 text-sm text-[var(--text-primary)]">
                    {getStatusLabel(detail.item.review_status, t)}
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                    {t("memory.curation.detail.navigation")}
                  </dt>
                  <dd className="mt-1">
                    <Link
                      href={mapHref}
                      className="inline-flex items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    >
                      {t("memory.curation.detail.viewOnMap")}
                      <ArrowUpRight className="h-4 w-4" />
                    </Link>
                  </dd>
                </div>
              </dl>
            </div>
            {detail.item.review_reason ? (
              <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
                <p className="text-[12px] uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
                  {t("memory.curation.detail.editorialReason")}
                </p>
                <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                  {detail.item.review_reason}
                </p>
              </div>
            ) : null}
          </DetailSection>

          <DetailSection eyebrow={t("memory.curation.detail.relatedAndDuplicates")}>
            <div className="grid gap-5 xl:grid-cols-2">
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {t("memory.curation.detail.relatedMemories")}
                </p>
                <div className="mt-3">
                  <MemoryReferenceList
                    items={detail.related_memories}
                    emptyLabel={t("memory.curation.detail.noStrongRelation")}
                    onSelectMemory={onSelectMemory}
                  />
                </div>
              </div>

              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {t("memory.curation.detail.possibleDuplicates")}
                </p>
                <div className="mt-3">
                  <MemoryReferenceList
                    items={detail.similar_memories}
                    emptyLabel={t("memory.curation.detail.noDuplicateDetected")}
                    onSelectMemory={onSelectMemory}
                  />
                </div>
              </div>
            </div>
          </DetailSection>

          <DetailSection eyebrow={t("memory.curation.detail.history")}>
            <ReviewHistory history={detail.history} />
          </DetailSection>
        </div>
      </div>
    </div>
  );
}

export function MemoryCurationDetail({
  kind,
  detail,
  loading = false,
  error,
  busy = false,
  onAction,
  onSelectMemory,
}: {
  kind: "memory" | "cluster";
  detail: MemoryReviewDetail | MemoryClusterReviewDetail | null;
  loading?: boolean;
  error?: string | null;
  busy?: boolean;
  onAction: (
    action: "approve" | "discard" | "expire" | "archive" | "restore" | "merge",
    options?: { duplicateOfMemoryId?: number | null }
  ) => void;
  onSelectMemory: (memoryId: number) => void;
}) {
  const { t } = useAppI18n();
  if (loading && !detail) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-5">
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className={cn("skeleton rounded-lg", index === 0 ? "h-24" : "h-24")} />
        ))}
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 text-center">
        <SearchX className="h-8 w-8 text-[var(--text-tertiary)]" />
        <p className="mt-4 text-base font-medium text-[var(--text-primary)]">
          {t("memory.curation.detail.loadDetailErrorTitle")}
        </p>
        <p className="mt-2 max-w-md text-sm leading-6 text-[var(--text-secondary)]">{error}</p>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 text-center">
        <DatabaseZap className="h-8 w-8 text-[var(--text-tertiary)]" />
        <p className="mt-4 text-base font-medium text-[var(--text-primary)]">
          {t("memory.curation.detail.selectEditorialItemTitle")}
        </p>
        <p className="mt-2 max-w-md text-sm leading-6 text-[var(--text-secondary)]">
          {t("memory.curation.detail.selectEditorialItemDescription")}
        </p>
      </div>
    );
  }

  const isMemoryDetail = "item" in detail;
  const isClusterDetail = "members" in detail;

  if (kind === "memory" && !isMemoryDetail) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 text-center">
        <DatabaseZap className="h-8 w-8 text-[var(--text-tertiary)]" />
        <p className="mt-4 text-base font-medium text-[var(--text-primary)]">
          {t("memory.curation.detail.loadingMemoryDetail")}
        </p>
      </div>
    );
  }

  if (kind === "cluster" && !isClusterDetail) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 text-center">
        <DatabaseZap className="h-8 w-8 text-[var(--text-tertiary)]" />
        <p className="mt-4 text-base font-medium text-[var(--text-primary)]">
          {t("memory.curation.detail.loadingClusterDetail")}
        </p>
      </div>
    );
  }

  return (
    <section className="flex min-h-0 flex-col overflow-hidden">
      {isMemoryDetail ? (
        <MemoryReviewDetailPane
          detail={detail}
          onAction={onAction}
          onSelectMemory={onSelectMemory}
          busy={busy}
        />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="shrink-0 border-b border-[var(--border-subtle)] bg-[rgba(12,12,12,0.9)] px-5 py-4">
            <div className="flex flex-col gap-3">
              <div className="min-w-0">
                <p className="eyebrow">{t("memory.curation.detail.learningTitle")}</p>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-[var(--text-secondary)]">
                  {t("memory.curation.detail.learningDescription")}
                </p>
              </div>
              <MemoryCurationActions kind="cluster" busy={busy} onAction={(action) => onAction(action)} />
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5" style={{ maxHeight: 'calc(100dvh - var(--shell-topbar-height) - 24rem)' }}>
            <MemoryClusterDetail
              detail={detail as MemoryClusterReviewDetail}
              onSelectMemory={onSelectMemory}
            />
          </div>
        </div>
      )}
    </section>
  );
}
