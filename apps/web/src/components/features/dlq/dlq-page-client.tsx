"use client";


import { useMemo, useState } from "react";
import { DatabaseZap, ShieldCheck } from "lucide-react";
import { DLQTable } from "@/components/dlq/dlq-table";
import { ErrorDetail } from "@/components/dlq/error-detail";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { ErrorState } from "@/components/ui/async-feedback";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  PageEmptyState,
  PageMetricStrip,
  PageMetricStripItem,
} from "@/components/ui/page-primitives";
import { SoftTabs } from "@/components/ui/soft-tabs";
import {
  formatAgentSelectionLabel,
  resolveAgentSelection,
} from "@/lib/agent-selection";
import { fetchControlPlaneDashboardJsonAllowError } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import type { DLQEntry } from "@/lib/types";
export default function DLQPage() {
  const { t } = useAppI18n();
  const { agents } = useAgentCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [selectedEntry, setSelectedEntry] = useState<DLQEntry | null>(null);
  const [retryFilter, setRetryFilter] = useState<string>("");
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const entriesQuery = useControlPlaneQuery<{
    items: DLQEntry[];
    unavailable: boolean;
  }>({
    tier: "live",
    queryKey: queryKeys.dashboard.dlq({
      agentIds: visibleBotIds,
      retryFilter,
      limit: 100,
    }),
    queryFn: async ({ signal }) => {
      const response = await fetchControlPlaneDashboardJsonAllowError<DLQEntry[]>(
        "/dlq",
        {
          signal,
          params: {
            agent: visibleBotIds,
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
  const selectionLabel = formatAgentSelectionLabel(visibleBotIds, agents);
  const retryEligibleCount = entries.filter(
    (entry) => entry.retry_eligible === 1 && !entry.retried_at
  ).length;
  const retriedCount = entries.filter((entry) => Boolean(entry.retried_at)).length;
  const affectedAgents = new Set(entries.map((entry) => entry.bot_id).filter(Boolean)).size;

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
        <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
          <div className="w-full md:w-[220px] md:flex-none">
            <AgentSwitcher
              multiple
              singleRow
              className="agent-switcher--compact"
              selectedBotIds={selectedBotIds}
              onSelectionChange={setSelectedBotIds}
            />
          </div>
          <div className="w-full md:w-auto md:shrink-0 md:ml-auto">
            <SoftTabs
              items={filterButtons.map((filter) => ({
                id: filter.value || "__all__",
                label: filter.label,
              }))}
              value={retryFilter || "__all__"}
              onChange={(id) => setRetryFilter(id === "__all__" ? "" : id)}
              ariaLabel={t("dlq.page.all")}
            />
          </div>
        </div>

        {loading && entries.length === 0 ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="flex h-[72px] animate-pulse flex-col gap-2 rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)] p-4"
                >
                  <div className="h-3 w-16 rounded bg-[var(--panel-strong)]" />
                  <div className="h-5 w-12 rounded bg-[var(--panel-strong)]" />
                </div>
              ))}
            </div>
            <div className="min-h-[320px]" />
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
            <PageMetricStrip className="animate-in stagger-1">
              <PageMetricStripItem
                label={t("dlq.page.visibleFailures")}
                value={`${entries.length}`}
                hint={loading ? t("common.loading") : t("dlq.page.orderedByRecent")}
              />
              <PageMetricStripItem
                label={t("dlq.page.retryEligible")}
                value={`${retryEligibleCount}`}
                hint={t("dlq.page.retryEligibleHint")}
              />
              <PageMetricStripItem
                label={t("dlq.page.alreadyRetried")}
                value={`${retriedCount}`}
                hint={t("dlq.page.alreadyRetriedHint")}
              />
              <PageMetricStripItem
                label={t("dlq.page.affectedAgents")}
                value={`${affectedAgents}`}
                hint={selectionLabel}
              />
            </PageMetricStrip>

            {unavailable ? (
              <div className="animate-in stagger-2 px-6 py-10">
                <PageEmptyState
                  icon={DatabaseZap}
                  title={t("dlq.page.unavailable")}
                  description={t("dlq.page.unavailableDescription")}
                />
              </div>
            ) : entries.length === 0 ? (
              <div className="animate-in stagger-2 px-6 py-10">
                <PageEmptyState
                  icon={ShieldCheck}
                  title={emptyTitle}
                  description={emptyDescription}
                />
              </div>
            ) : (
              <div className="animate-in stagger-2">
                <DLQTable
                  entries={entries}
                  onEntryClick={setSelectedEntry}
                  selectedEntryId={selectedEntry?.id ?? null}
                />
              </div>
            )}
          </>
        )}
      </div>

      <ErrorDetail entry={selectedEntry} onClose={() => setSelectedEntry(null)} />
    </>
  );
}
