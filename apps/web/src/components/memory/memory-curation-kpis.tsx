"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import type { MemoryCurationOverview } from "@/lib/types";

function formatCount(value: number, locale: string) {
  return new Intl.NumberFormat(locale).format(value);
}

export function MemoryCurationKpis({
  overview,
}: {
  overview: MemoryCurationOverview;
}) {
  const { t, language } = useAppI18n();
  const cards = [
    {
      label: t("memory.curation.kpis.pendingMemories"),
      value: overview.pending_memories,
      meta: t("memory.curation.kpis.pendingMemoriesMeta"),
    },
    {
      label: t("memory.curation.kpis.pendingClusters"),
      value: overview.pending_clusters,
      meta: t("memory.curation.kpis.pendingClustersMeta"),
    },
    {
      label: t("memory.curation.kpis.expiringSoon"),
      value: overview.expiring_soon,
      meta: t("memory.curation.kpis.expiringSoonMeta"),
    },
    {
      label: t("memory.curation.kpis.reviewed7d"),
      value:
        overview.approved_last_7d +
        overview.merged_last_7d +
        overview.discarded_last_7d,
      meta: t("memory.curation.kpis.reviewed7dMeta", {
        approved: overview.approved_last_7d,
        merged: overview.merged_last_7d,
        discarded: overview.discarded_last_7d,
      }),
    },
  ];

  return (
    <section className="glass-card-sm overflow-hidden p-0">
      <div className="grid gap-px bg-[var(--border-subtle)] md:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="bg-[var(--surface-elevated)] px-4 py-3 sm:px-5"
          >
            <p className="eyebrow text-[11px] text-[var(--text-quaternary)]">{card.label}</p>
            <div className="mt-1.5 flex items-end justify-between gap-4">
              <p className="text-[1.55rem] font-semibold tracking-[-0.06em] text-[var(--text-primary)]">
                {formatCount(card.value, language)}
              </p>
            </div>
            <p className="mt-1 text-[11.5px] leading-5 text-[var(--text-tertiary)]">
              {card.meta}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
