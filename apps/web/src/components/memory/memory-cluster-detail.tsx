"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getBotLabel } from "@/lib/bot-constants";
import { getMemoryTypeLabel, getMemoryTypeMeta } from "@/lib/memory-constants";
import type { MemoryClusterReviewDetail } from "@/lib/types";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";

function getClusterStatusLabel(
  status: MemoryClusterReviewDetail["cluster"]["review_status"],
  t: (key: string, options?: Record<string, unknown>) => string
) {
  return t(`memory.curation.status.${status}`, { defaultValue: status });
}

function ClusterHistory({
  detail,
}: {
  detail: MemoryClusterReviewDetail;
}) {
  const { t } = useAppI18n();
  if (detail.history.length === 0) {
    return <p className="text-sm leading-6 text-[var(--text-secondary)]">{t("memory.curation.detail.noReviewRecorded")}</p>;
  }

  return (
    <div className="divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.012)]">
      {detail.history.map((entry) => (
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

export function MemoryClusterDetail({
  detail,
  onSelectMemory,
}: {
  detail: MemoryClusterReviewDetail;
  onSelectMemory: (memoryId: number) => void;
}) {
  const { t } = useAppI18n();
  const typeMeta = getMemoryTypeMeta(detail.cluster.dominant_type);
  const mapHref = `/memory?bot=${detail.cluster.bot_id}&search=${encodeURIComponent(
    detail.cluster.summary
  )}`;

  return (
    <div className="space-y-5">
      <section className="border-t-0 pt-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--text-tertiary)]">
          <span
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1"
            style={{
              color: typeMeta.color,
              backgroundColor: `color-mix(in srgb, ${typeMeta.color} 10%, transparent)`,
            }}
            >
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: typeMeta.color }} />
            {getMemoryTypeLabel(detail.cluster.dominant_type, t)}
          </span>
          <span>{getBotLabel(detail.cluster.bot_id)}</span>
          <span>•</span>
          <span>{t("memory.map.memoryCount", { count: detail.cluster.member_count })}</span>
          <span>•</span>
          <span>{detail.cluster.session_ids.length} {t("memory.inspector.sessions").toLowerCase()}</span>
          {detail.cluster.semantic_strength != null ? (
            <>
              <span>•</span>
              <span>{Math.round(detail.cluster.semantic_strength * 100)}%</span>
            </>
          ) : null}
        </div>

        <p className="mt-4 text-[15px] leading-7 text-[var(--text-primary)]">
          {detail.cluster.summary}
        </p>
      </section>

      <section className="border-t border-[var(--border-subtle)] pt-5">
        <p className="eyebrow">{t("memory.curation.detail.groupingContext")}</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <p className="text-[12px] uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
              {t("memory.curation.detail.created")}
            </p>
            <p className="mt-1 text-sm text-[var(--text-primary)]">
              {formatDateTime(detail.cluster.created_at)}
            </p>
          </div>
          <div>
            <p className="text-[12px] uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
              {t("memory.curation.detail.sessionsCovered")}
            </p>
            <p className="mt-1 text-sm text-[var(--text-primary)]">
              {detail.overlaps.length}
            </p>
          </div>
          <div>
            <p className="text-[12px] uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
              {t("memory.curation.detail.editorialStatus")}
            </p>
            <p className="mt-1 text-sm text-[var(--text-primary)]">
              {getClusterStatusLabel(detail.cluster.review_status, t)}
            </p>
          </div>
          <div>
            <p className="text-[12px] uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
              {t("memory.curation.detail.navigation")}
            </p>
            <Link
              href={mapHref}
              className="mt-1 inline-flex items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              {t("memory.curation.detail.viewOnMap")}
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      <section className="border-t border-[var(--border-subtle)] pt-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <div>
            <p className="eyebrow">{t("memory.curation.detail.primaryMembers")}</p>
            <div className="mt-3 divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.012)]">
              {detail.members.map((member) => (
                <button
                  key={member.memory_id}
                  type="button"
                  onClick={() => onSelectMemory(member.memory_id)}
                  className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-[rgba(255,255,255,0.018)]"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                      {member.title}
                    </p>
                    <p className="mt-1 line-clamp-2 text-sm leading-6 text-[var(--text-secondary)]">
                      {member.content}
                    </p>
                  </div>
                  <span className="shrink-0 text-[11px] text-[var(--text-tertiary)]">
                    {formatRelativeTime(member.last_accessed ?? member.created_at)}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="eyebrow">{t("memory.curation.detail.sessionsCovered")}</p>
            <div className="mt-3 divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.012)]">
              {detail.overlaps.length === 0 ? (
                <div className="px-4 py-3 text-sm text-[var(--text-secondary)]">
                  {t("memory.curation.detail.noLinkedSessions")}
                </div>
              ) : (
                detail.overlaps.map((entry) => (
                  <div
                    key={entry.session_id}
                    className="flex items-center justify-between gap-3 px-4 py-3"
                  >
                    <span className="truncate text-sm text-[var(--text-primary)]">
                      {entry.session_id}
                    </span>
                    <span className="shrink-0 text-[11px] text-[var(--text-tertiary)]">
                      {t("memory.map.memoryCount", { count: entry.count })}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="border-t border-[var(--border-subtle)] pt-5">
        <p className="eyebrow">{t("memory.curation.detail.history")}</p>
        <div className="mt-3">
          <ClusterHistory detail={detail} />
        </div>
      </section>
    </div>
  );
}
