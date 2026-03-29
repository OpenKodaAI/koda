"use client";

import { useEffect, useMemo, useState } from "react";
import { Clock3, DatabaseZap } from "lucide-react";
import { CronTable } from "@/components/schedules/cron-table";
import { BotSwitcher } from "@/components/layout/bot-switcher";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  PageEmptyState,
  PageSection,
  PageSectionHeader,
  PageStatCard,
  PageStatGrid,
} from "@/components/ui/page-primitives";
import { formatBotSelectionLabel, resolveBotSelection } from "@/lib/bot-selection";
import { fetchControlPlaneDashboardJsonAllowError } from "@/lib/control-plane-dashboard";
import type { CronJob } from "@/lib/types";

export default function SchedulesPage() {
  const { t } = useAppI18n();
  const { bots } = useBotCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [jobsByBot, setJobsByBot] = useState<Record<string, CronJob[]>>({});
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const visibleBotIds = useMemo(
    () => resolveBotSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const selectionLabel = formatBotSelectionLabel(visibleBotIds, bots);

  useEffect(() => {
    async function fetchCronJobs() {
      setLoading(true);
      setUnavailable(false);
      try {
        const response = await fetchControlPlaneDashboardJsonAllowError<
          Array<CronJob & { bot_id?: string | null }>
        >("/schedules", {
          params: {
            bot: visibleBotIds,
          },
          fallbackError: t("schedules.page.unavailableDescription", {
            defaultValue: "Unable to load canonical schedules.",
          }),
        });

        const results: Record<string, CronJob[]> = {};
        for (const bot of bots) {
          results[bot.id] = [];
        }

        for (const job of Array.isArray(response.data) ? response.data : []) {
          if (!job.bot_id || !results[job.bot_id]) {
            continue;
          }
          results[job.bot_id].push(job);
        }

        setJobsByBot(results);
        setUnavailable(!response.ok);
      } catch {
        setJobsByBot({});
        setUnavailable(true);
      } finally {
        setLoading(false);
      }
    }

    void fetchCronJobs();
  }, [bots, t, visibleBotIds]);

  const visibleBots = useMemo(
    () =>
      bots.filter((bot) => visibleBotIds.includes(bot.id)).map((bot) => ({
        bot,
        jobs: jobsByBot[bot.id] || [],
      })),
    [bots, jobsByBot, visibleBotIds]
  );

  const totalJobs = visibleBots.reduce((sum, entry) => sum + entry.jobs.length, 0);
  const enabledJobs = visibleBots.reduce(
    (sum, entry) => sum + entry.jobs.filter((job) => job.enabled === 1).length,
    0
  );
  const disabledJobs = totalJobs - enabledJobs;
  const botsWithJobs = visibleBots.filter((entry) => entry.jobs.length > 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 md:flex-row md:flex-wrap xl:flex-nowrap xl:items-center">
        <div className="w-full md:max-w-[350px] md:min-w-[200px] xl:w-[320px] xl:flex-none">
          <BotSwitcher
            multiple
            selectedBotIds={selectedBotIds}
            onSelectionChange={setSelectedBotIds}
          />
        </div>
        <div className="flex flex-1 flex-wrap items-center justify-start gap-2 md:justify-end">
          <span className="chip">
            {loading ? t("common.loading") : t("schedules.jobs", { count: totalJobs, defaultValue: "{{count}} schedules" })}
          </span>
          <span className="chip">{t("schedules.active", { count: enabledJobs, defaultValue: "{{count}} active" })}</span>
          <span className="chip">{selectionLabel}</span>
        </div>
      </div>

      {loading ? (
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
      ) : (
        <>
          <PageStatGrid className="app-kpi-grid--four-up animate-in stagger-1">
            <PageStatCard
              label={t("schedules.page.visibleBots")}
              value={`${visibleBots.length}`}
              hint={selectionLabel}
            />
            <PageStatCard
              label={t("schedules.page.withSchedule")}
              value={`${botsWithJobs.length}`}
              hint={t("schedules.page.withAtLeastOne")}
            />
            <PageStatCard
              label={t("schedules.page.enabled")}
              value={`${enabledJobs}`}
              hint={t("schedules.page.runningNormally")}
            />
            <PageStatCard
              label={t("schedules.page.paused")}
              value={`${disabledJobs}`}
              hint={t("schedules.page.registeredDisabled")}
            />
          </PageStatGrid>

          <PageSection className="animate-in stagger-2 px-5 py-5 lg:px-6">
            <PageSectionHeader
              eyebrow={t("routeMeta.schedules.title")}
              title={t("schedules.page.title")}
              description={t("schedules.page.description")}
              meta={
                <div className="app-filter-row">
                  <span className="chip">{t("schedules.page.routines", { count: totalJobs })}</span>
                  <span className="chip">{t("schedules.page.active", { count: enabledJobs })}</span>
                </div>
              }
            />

            {unavailable ? (
              <PageEmptyState
                icon={DatabaseZap}
                title={t("schedules.page.unavailable", {
                  defaultValue: "Canonical scheduler data unavailable",
                })}
                description={t("schedules.page.unavailableDescription", {
                  defaultValue:
                    "The control-plane/runtime APIs do not expose per-bot cron inventory in this deployment.",
                })}
              />
            ) : botsWithJobs.length === 0 ? (
              <PageEmptyState
                icon={Clock3}
                title={t("schedules.page.noVisible")}
                description={t("schedules.page.noVisibleDescription")}
              />
            ) : (
              <section
                className={`grid gap-4 ${
                  botsWithJobs.length > 1 ? "xl:grid-cols-2" : "grid-cols-1"
                }`}
              >
                {botsWithJobs.map((entry, index) => {
                  const activeCount = entry.jobs.filter((job) => job.enabled === 1).length;
                  const pausedCount = entry.jobs.length - activeCount;

                  return (
                    <div
                      key={entry.bot.id}
                      className={`app-section animate-in stagger-${Math.min(index + 1, 6)} overflow-hidden px-0 py-0`}
                    >
                      <div className="border-b border-[var(--border-subtle)] px-5 py-4 lg:px-6">
                        <PageSectionHeader
                          eyebrow={entry.bot.label}
                          title={t("schedules.page.configured", {
                            count: entry.jobs.length,
                            defaultValue: "{{count}} configured",
                          })}
                          description={t("schedules.page.configuredDescription")}
                          meta={
                            <div className="app-filter-row">
                              <span className="chip">{t("schedules.page.active", { count: activeCount })}</span>
                              <span className="chip">{t("schedules.page.pausedCount", { count: pausedCount })}</span>
                            </div>
                          }
                          className="mb-0"
                        />
                      </div>

                      <div className="p-5 lg:p-6">
                        <CronTable
                          jobs={entry.jobs}
                          botLabel={entry.bot.label}
                          botColor={entry.bot.color}
                        />
                      </div>
                    </div>
                  );
                })}
              </section>
            )}
          </PageSection>
        </>
      )}
    </div>
  );
}
