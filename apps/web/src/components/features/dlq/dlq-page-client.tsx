"use client";


import { useMemo, useState } from "react";
import { DatabaseZap, ShieldCheck } from "lucide-react";
import { DLQTable } from "@/components/dlq/dlq-table";
import { ErrorDetail } from "@/components/dlq/error-detail";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { ErrorState } from "@/components/ui/async-feedback";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  PageEmptyState,
  PageFilterChips,
  PageSection,
  PageSectionHeader,
  PageStatCard,
  PageStatGrid,
} from "@/components/ui/page-primitives";
import {
  formatBotSelectionLabel,
  resolveBotSelection,
} from "@/lib/bot-selection";
import { fetchControlPlaneDashboardJsonAllowError } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type { DLQEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function DLQPage() {
  const { t } = useAppI18n();
  const { bots } = useBotCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [selectedEntry, setSelectedEntry] = useState<DLQEntry | null>(null);
  const [retryFilter, setRetryFilter] = useState<string>("");
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const visibleBotIds = useMemo(
    () => resolveBotSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const entriesQuery = useControlPlaneQuery<{
    items: DLQEntry[];
    unavailable: boolean;
  }>({
    tier: "live",
    queryKey: queryKeys.dashboard.dlq({
      botIds: visibleBotIds,
      retryFilter,
      limit: 100,
    }),
    queryFn: async ({ signal }) => {
      const response = await fetchControlPlaneDashboardJsonAllowError<DLQEntry[]>(
        "/dlq",
        {
          signal,
          params: {
            bot: visibleBotIds,
            limit: 100,
            retryEligible:
              retryFilter === "eligible"
                ? true
                : retryFilter === "ineligible"
                  ? false
                  : null,
          },
          fallbackError: t("dlq.page.unavailableDescription"),
        },
      );

      const merged = (Array.isArray(response.data) ? response.data : [])
        .sort(
          (left, right) =>
            new Date(right.failed_at).getTime() - new Date(left.failed_at).getTime()
        );

      return {
        items: merged,
        unavailable: !response.ok,
      };
    },
  });
  const entries = entriesQuery.data?.items ?? [];
  const loading = entriesQuery.isLoading;
  const unavailable = entriesQuery.data?.unavailable ?? false;
  const selectionLabel = formatBotSelectionLabel(visibleBotIds, bots);
  const retryEligibleCount = entries.filter(
    (entry) => entry.retry_eligible === 1 && !entry.retried_at
  ).length;
  const retriedCount = entries.filter((entry) => Boolean(entry.retried_at)).length;
  const affectedBots = new Set(entries.map((entry) => entry.bot_id).filter(Boolean)).size;

  const filterButtons = [
    { value: "", label: t("dlq.page.all") },
    { value: "eligible", label: t("dlq.page.retryEligible") },
    { value: "ineligible", label: t("dlq.page.noRetry") },
  ];

  const emptyTitle =
    retryFilter === "eligible"
      ? t("dlq.page.emptyEligible")
      : retryFilter === "ineligible"
        ? t("dlq.page.emptyIneligible")
        : t("dlq.page.emptyDefault");
  const emptyDescription =
    retryFilter === "eligible"
      ? t("dlq.page.emptyEligibleDescription")
      : retryFilter === "ineligible"
        ? t("dlq.page.emptyIneligibleDescription")
        : t("dlq.page.emptyDefaultDescription");

  return (
    <>
      <div className="space-y-4">
        <div className="flex flex-col gap-4 md:flex-row md:flex-wrap xl:flex-nowrap xl:items-center">
          <div className="w-full md:max-w-[350px] md:min-w-[200px] xl:w-[320px] xl:flex-none">
            <BotSwitcher
              multiple
              selectedBotIds={selectedBotIds}
              onSelectionChange={setSelectedBotIds}
            />
          </div>
          <PageFilterChips className="min-w-0 flex-1 items-center justify-start md:justify-end">
            {filterButtons.map((filter) => (
              <button
                key={filter.value}
                type="button"
                onClick={() => setRetryFilter(filter.value)}
                className={cn("button-pill", retryFilter === filter.value && "is-active")}
              >
                {filter.label}
              </button>
            ))}
            <span className="chip">{!loading ? t("dlq.page.failures", { count: entries.length }) : t("common.loading")}</span>
            <span className="chip">{selectionLabel}</span>
          </PageFilterChips>
        </div>

        {loading && entries.length === 0 ? (
          <div className="space-y-4">
            {/* Controls bar */}
            <div className="flex flex-col gap-4 md:flex-row md:flex-wrap xl:flex-nowrap xl:items-center">
              <div className="w-full md:max-w-[350px] md:min-w-[200px] xl:w-[320px] xl:flex-none">
                <div className="skeleton h-11 w-full rounded-xl" />
              </div>
              <div className="flex flex-1 flex-wrap items-center justify-start gap-2 md:justify-end">
                <div className="skeleton h-7 w-20 rounded-full" />
                <div className="skeleton h-7 w-20 rounded-full" />
                <div className="skeleton h-7 w-16 rounded-full" />
              </div>
            </div>

            {/* Stat grid */}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="glass-card-sm p-5">
                  <div className="skeleton skeleton-text mb-3" style={{ width: "40%" }} />
                  <div className="skeleton skeleton-heading mb-2" style={{ width: "50%" }} />
                  <div className="skeleton skeleton-text" style={{ width: "65%" }} />
                </div>
              ))}
            </div>

            {/* Table section */}
            <div className="app-section min-h-[400px] p-5 sm:p-6" />
          </div>
        ) : entriesQuery.error ? (
          <ErrorState
            title={t("dlq.page.unavailable")}
            description={entriesQuery.error.message ?? t("dlq.page.unavailableDescription")}
            onRetry={() => {
              void entriesQuery.refetch();
            }}
          />
        ) : (
          <>
            <PageStatGrid className="app-kpi-grid--four-up animate-in stagger-1">
              <PageStatCard
                label={t("dlq.page.visibleFailures")}
                value={`${entries.length}`}
                hint={loading ? t("common.loading") : t("dlq.page.orderedByRecent")}
              />
              <PageStatCard
                label={t("dlq.page.retryEligible")}
                value={`${retryEligibleCount}`}
                hint={t("dlq.page.retryEligibleHint")}
              />
              <PageStatCard
                label={t("dlq.page.alreadyRetried")}
                value={`${retriedCount}`}
                hint={t("dlq.page.alreadyRetriedHint")}
              />
              <PageStatCard
                label={t("dlq.page.affectedBots")}
                value={`${affectedBots}`}
                hint={selectionLabel}
              />
            </PageStatGrid>

            <PageSection className="animate-in stagger-2 overflow-hidden px-0 py-0">
              <div className="px-5 py-5 lg:px-6">
                <PageSectionHeader
                  eyebrow={t("routeMeta.dlq.title")}
                  title={t("dlq.page.actionTitle")}
                  description={t("dlq.page.actionDescription")}
                  meta={
                    <div className="app-filter-row">
                      <span className="chip">
                        {filterButtons.find((item) => item.value === retryFilter)?.label}
                      </span>
                      <span className="chip">{selectionLabel}</span>
                    </div>
                  }
                />
              </div>

              {unavailable ? (
                <div className="border-t border-[var(--border-subtle)] px-6 py-10">
                  <PageEmptyState
                    icon={DatabaseZap}
                    title={t("dlq.page.unavailable")}
                    description={t("dlq.page.unavailableDescription")}
                  />
                </div>
              ) : entries.length === 0 ? (
                <div className="border-t border-[var(--border-subtle)] px-6 py-10">
                  <PageEmptyState
                    icon={ShieldCheck}
                    title={emptyTitle}
                    description={emptyDescription}
                  />
                </div>
              ) : (
                <div className="border-t border-[var(--border-subtle)]">
                  <DLQTable
                    entries={entries}
                    onEntryClick={setSelectedEntry}
                    selectedEntryId={selectedEntry?.id ?? null}
                  />
                </div>
              )}
            </PageSection>
          </>
        )}
      </div>

      <ErrorDetail entry={selectedEntry} onClose={() => setSelectedEntry(null)} />
    </>
  );
}
