"use client";

import { PageMetricStrip, PageMetricStripItem } from "@/components/ui/page-primitives";
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
  return (
    <PageMetricStrip>
      <PageMetricStripItem
        label={t("memory.curation.kpis.pendingMemories")}
        value={formatCount(overview.pending_memories, language)}
        hint={t("memory.curation.kpis.pendingMemoriesMeta")}
      />
      <PageMetricStripItem
        label={t("memory.curation.kpis.pendingClusters")}
        value={formatCount(overview.pending_clusters, language)}
        hint={t("memory.curation.kpis.pendingClustersMeta")}
      />
      <PageMetricStripItem
        label={t("memory.curation.kpis.expiringSoon")}
        value={formatCount(overview.expiring_soon, language)}
        hint={t("memory.curation.kpis.expiringSoonMeta")}
      />
      <PageMetricStripItem
        label={t("memory.curation.kpis.reviewed7d")}
        value={formatCount(
          overview.approved_last_7d +
            overview.merged_last_7d +
            overview.discarded_last_7d,
          language,
        )}
        hint={t("memory.curation.kpis.reviewed7dMeta", {
          approved: overview.approved_last_7d,
          merged: overview.merged_last_7d,
          discarded: overview.discarded_last_7d,
        })}
      />
    </PageMetricStrip>
  );
}
