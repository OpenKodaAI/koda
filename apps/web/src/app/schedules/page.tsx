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
import type { CronJob, ScheduleDetail } from "@/lib/types";

type ScheduleEditDraft = {
  triggerType: string;
  scheduleExpr: string;
  timezone: string;
  content: string;
  description: string;
  workDir: string;
  provider: string;
  model: string;
  notificationMode: string;
  verificationMode: string;
};

function getLifecycleAction(job: CronJob | null): "pause" | "resume" | "validate" | null {
  if (!job) {
    return null;
  }
  switch (job.status) {
    case "active":
      return "pause";
    case "paused":
    case "validated":
    case "failed_open":
      return "resume";
    case "validation_pending":
      return "validate";
    default:
      return job.enabled === 1 ? "pause" : "resume";
  }
}

function getLifecycleLabel(job: CronJob | null): string {
  if (!job) {
    return "Update job";
  }
  switch (job.status) {
    case "active":
      return "Pause job";
    case "paused":
      return "Resume job";
    case "validated":
      return "Activate job";
    case "failed_open":
      return "Resume failed-open job";
    case "validation_pending":
      return "Queue validation";
    default:
      return job.enabled === 1 ? "Pause job" : "Activate or resume";
  }
}

function buildDraft(detail: ScheduleDetail): ScheduleEditDraft {
  const payload = detail.job.payload || {};
  return {
    triggerType: detail.job.trigger_type || "interval",
    scheduleExpr: detail.job.schedule_expr || detail.job.cron_expression,
    timezone: detail.job.timezone || "UTC",
    content:
      String(
        payload.query ||
          payload.text ||
          payload.command ||
          detail.job.summary ||
          detail.job.command ||
          ""
      ) || "",
    description: String(payload.description || detail.job.description || ""),
    workDir: detail.job.work_dir || "",
    provider: detail.job.provider_preference || "",
    model: detail.job.model_preference || "",
    notificationMode:
      String(detail.job.notification_policy?.mode || "summary_complete") || "summary_complete",
    verificationMode:
      String(detail.job.verification_policy?.mode || "post_write_if_any") || "post_write_if_any",
  };
}

function buildPatch(detail: ScheduleDetail, draft: ScheduleEditDraft) {
  const patch: Record<string, unknown> = {
    trigger_type: draft.triggerType,
    schedule_expr: draft.scheduleExpr,
    timezone: draft.timezone,
    work_dir: draft.workDir,
    notification_policy: { mode: draft.notificationMode },
    verification_policy: { mode: draft.verificationMode },
  };

  if (draft.provider.trim()) {
    patch.provider = draft.provider.trim();
  }
  if (draft.model.trim()) {
    patch.model = draft.model.trim();
  }

  if (detail.job.job_type === "agent_query") {
    patch.query = draft.content;
  } else if (detail.job.job_type === "reminder") {
    patch.text = draft.content;
  } else {
    patch.command = draft.content;
    patch.description = draft.description;
  }

  return patch;
}

export default function SchedulesPage() {
  const { t } = useAppI18n();
  const { bots } = useBotCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [jobsByBot, setJobsByBot] = useState<Record<string, CronJob[]>>({});
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [selectedJob, setSelectedJob] = useState<CronJob | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<ScheduleDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [busyJobId, setBusyJobId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<ScheduleEditDraft | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const visibleBotIds = useMemo(
    () => resolveBotSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const selectionLabel = formatBotSelectionLabel(visibleBotIds, bots);

  useEffect(() => {
    async function fetchSchedules() {
      setLoading(true);
      setUnavailable(false);
      try {
        const response = await fetchControlPlaneDashboardJsonAllowError<CronJob[]>("/schedules", {
          params: { bot: visibleBotIds },
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

    void fetchSchedules();
  }, [bots, t, visibleBotIds, refreshNonce]);

  async function loadDetail(job: CronJob) {
    if (!job.bot_id) return;
    setSelectedJob(job);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const response = await fetch(`/api/runtime/bots/${job.bot_id}/schedules/${job.id}`, {
        cache: "no-store",
      });
      const payload = (await response.json()) as ScheduleDetail | { error?: string };
      if (!response.ok) {
        throw new Error("error" in payload ? payload.error || "Unable to load schedule" : "Unable to load schedule");
      }
      const detail = payload as ScheduleDetail;
      setSelectedDetail(detail);
      setEditDraft(buildDraft(detail));
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "Unable to load schedule detail");
      setSelectedDetail(null);
      setEditDraft(null);
    } finally {
      setDetailLoading(false);
    }
  }

  async function runAction(job: CronJob, action: "pause" | "resume" | "run" | "validate" | "delete") {
    if (!job.bot_id) return;
    setBusyJobId(job.id);
    setStatusMessage(null);
    try {
      const response = await fetch(`/api/runtime/bots/${job.bot_id}/schedules/${job.id}/actions/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: job.user_id }),
      });
      const payload = (await response.json()) as
        | ({ message?: string } & Partial<ScheduleDetail>)
        | { error?: string };
      if (!response.ok) {
        throw new Error("error" in payload ? payload.error || "Unable to operate on schedule" : "Unable to operate on schedule");
      }
      setStatusMessage((payload as { message?: string }).message || "Schedule updated.");
      if ("job" in payload && payload.job) {
        setSelectedDetail(payload as ScheduleDetail);
        setSelectedJob((payload as ScheduleDetail).job);
        setEditDraft(buildDraft(payload as ScheduleDetail));
      } else {
        await loadDetail(job);
      }
      setRefreshNonce((value) => value + 1);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to operate on schedule");
    } finally {
      setBusyJobId(null);
    }
  }

  async function saveEdit() {
    if (!selectedJob?.bot_id || !selectedDetail || !editDraft) {
      return;
    }
    setBusyJobId(selectedJob.id);
    setStatusMessage(null);
    try {
      const response = await fetch(`/api/runtime/bots/${selectedJob.bot_id}/schedules/${selectedJob.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: selectedDetail.job.user_id,
          expected_config_version: selectedDetail.job.config_version,
          reason: "Updated from schedules page",
          patch: buildPatch(selectedDetail, editDraft),
        }),
      });
      const payload = (await response.json()) as
        | ({ message?: string } & Partial<ScheduleDetail>)
        | { error?: string };
      if (!response.ok) {
        throw new Error("error" in payload ? payload.error || "Unable to update schedule" : "Unable to update schedule");
      }
      setStatusMessage((payload as { message?: string }).message || "Schedule updated.");
      if ("job" in payload && payload.job) {
        setSelectedDetail(payload as ScheduleDetail);
        setSelectedJob((payload as ScheduleDetail).job);
        setEditDraft(buildDraft(payload as ScheduleDetail));
      }
      setRefreshNonce((value) => value + 1);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to update schedule");
    } finally {
      setBusyJobId(null);
    }
  }

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
          <BotSwitcher multiple selectedBotIds={selectedBotIds} onSelectionChange={setSelectedBotIds} />
        </div>
        <div className="flex flex-1 flex-wrap items-center justify-start gap-2 md:justify-end">
          <span className="chip">
            {loading
              ? t("common.loading")
              : t("schedules.jobs", { count: totalJobs, defaultValue: "{{count}} schedules" })}
          </span>
          <span className="chip">{t("schedules.active", { count: enabledJobs, defaultValue: "{{count}} active" })}</span>
          <span className="chip">{selectionLabel}</span>
        </div>
      </div>

      {statusMessage ? (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-4 py-3 text-sm text-[var(--text-secondary)]">
          {statusMessage}
        </div>
      ) : null}

      {loading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="glass-card-sm p-5">
                <div className="skeleton skeleton-text mb-3" style={{ width: "40%" }} />
                <div className="skeleton skeleton-heading mb-2" style={{ width: "50%" }} />
                <div className="skeleton skeleton-text" style={{ width: "65%" }} />
              </div>
            ))}
          </div>
          <div className="app-section min-h-[400px] p-5 sm:p-6" />
        </div>
      ) : (
        <>
          <PageStatGrid className="app-kpi-grid--four-up animate-in stagger-1">
            <PageStatCard label={t("schedules.page.visibleBots")} value={`${visibleBots.length}`} hint={selectionLabel} />
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
                          busyJobId={busyJobId}
                          onInspect={(job) => void loadDetail(job)}
                          onEdit={(job) => void loadDetail(job)}
                          onRun={(job) => void runAction(job, "run")}
                          onLifecycleAction={(job, action) => void runAction(job, action)}
                        />
                      </div>
                    </div>
                  );
                })}
              </section>
            )}
          </PageSection>

          {selectedJob ? (
            <PageSection className="animate-in stagger-3 px-5 py-5 lg:px-6">
              <PageSectionHeader
                eyebrow="Inspector"
                title={`Job #${selectedJob.id}`}
                description={selectedJob.summary || selectedJob.command || "Schedule detail"}
                meta={
                  <div className="app-filter-row">
                    <span className="chip">{selectedJob.job_type || "job"}</span>
                    <span className="chip">{selectedJob.trigger_type || "trigger"}</span>
                    <span className="chip">{selectedJob.status || "unknown"}</span>
                  </div>
                }
              />

              {detailLoading ? (
                <div className="text-sm text-[var(--text-secondary)]">Loading schedule detail…</div>
              ) : detailError ? (
                <div className="text-sm text-[var(--text-secondary)]">{detailError}</div>
              ) : selectedDetail && editDraft ? (
                <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                  <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-4">
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="text-sm text-[var(--text-secondary)]">
                        Trigger
                        <select
                          className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                          value={editDraft.triggerType}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current ? { ...current, triggerType: event.target.value } : current
                            )
                          }
                        >
                          <option value="one_shot">One-shot</option>
                          <option value="interval">Interval</option>
                          <option value="cron">Cron</option>
                        </select>
                      </label>
                      <label className="text-sm text-[var(--text-secondary)]">
                        Timezone
                        <input
                          className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                          value={editDraft.timezone}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current ? { ...current, timezone: event.target.value } : current
                            )
                          }
                        />
                      </label>
                      <label className="text-sm text-[var(--text-secondary)] md:col-span-2">
                        Schedule expression
                        <input
                          className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                          value={editDraft.scheduleExpr}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current ? { ...current, scheduleExpr: event.target.value } : current
                            )
                          }
                        />
                      </label>
                      <label className="text-sm text-[var(--text-secondary)] md:col-span-2">
                        {selectedDetail.job.job_type === "reminder"
                          ? "Reminder text"
                          : selectedDetail.job.job_type === "shell_command"
                            ? "Command"
                            : "Query"}
                        <textarea
                          className="mt-1 min-h-[120px] w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                          value={editDraft.content}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current ? { ...current, content: event.target.value } : current
                            )
                          }
                        />
                      </label>
                      {selectedDetail.job.job_type === "shell_command" ? (
                        <label className="text-sm text-[var(--text-secondary)] md:col-span-2">
                          Description
                          <input
                            className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                            value={editDraft.description}
                            onChange={(event) =>
                              setEditDraft((current) =>
                                current ? { ...current, description: event.target.value } : current
                              )
                            }
                          />
                        </label>
                      ) : null}
                      <label className="text-sm text-[var(--text-secondary)]">
                        Work dir
                        <input
                          className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                          value={editDraft.workDir}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current ? { ...current, workDir: event.target.value } : current
                            )
                          }
                        />
                      </label>
                      <label className="text-sm text-[var(--text-secondary)]">
                        Notification mode
                        <select
                          className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                          value={editDraft.notificationMode}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current ? { ...current, notificationMode: event.target.value } : current
                            )
                          }
                        >
                          <option value="summary_complete">summary_complete</option>
                          <option value="failures_only">failures_only</option>
                          <option value="none">none</option>
                        </select>
                      </label>
                      <label className="text-sm text-[var(--text-secondary)]">
                        Verification mode
                        <select
                          className="mt-1 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                          value={editDraft.verificationMode}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current ? { ...current, verificationMode: event.target.value } : current
                            )
                          }
                        >
                          <option value="post_write_if_any">post_write_if_any</option>
                          <option value="task_success">task_success</option>
                        </select>
                      </label>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                        onClick={() => void saveEdit()}
                        disabled={busyJobId === selectedJob.id}
                      >
                        Save changes
                      </button>
                      <button
                        type="button"
                        className="rounded-xl border border-[var(--border-subtle)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)]"
                        onClick={() => void runAction(selectedJob, "validate")}
                        disabled={busyJobId === selectedJob.id}
                      >
                        Queue validation
                      </button>
                      <button
                        type="button"
                        className="rounded-xl border border-[var(--border-subtle)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)]"
                        onClick={() => {
                          const action = getLifecycleAction(selectedDetail.job);
                          if (action) {
                            void runAction(selectedJob, action);
                          }
                        }}
                        disabled={busyJobId === selectedJob.id}
                      >
                        {getLifecycleLabel(selectedDetail.job)}
                      </button>
                      <button
                        type="button"
                        className="rounded-xl border border-[var(--border-subtle)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)]"
                        onClick={() => void runAction(selectedJob, "delete")}
                        disabled={busyJobId === selectedJob.id}
                      >
                        Archive job
                      </button>
                      <button
                        type="button"
                        className="rounded-xl border border-[var(--border-subtle)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)]"
                        onClick={() => void loadDetail(selectedJob)}
                        disabled={busyJobId === selectedJob.id}
                      >
                        Refresh detail
                      </button>
                    </div>
                  </section>

                  <section className="space-y-4">
                    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-4">
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">Current status</h3>
                      <div className="mt-3 space-y-1 text-xs text-[var(--text-secondary)]">
                        <p>Status: {selectedDetail.job.status || "unknown"}</p>
                        <p>Next run: {selectedDetail.job.next_run_at || "pending validation"}</p>
                        <p>Version: {selectedDetail.job.config_version || 1}</p>
                        {selectedDetail.latest_task_runtime ? (
                          <>
                            <p>
                              Runtime task: {String(selectedDetail.latest_task_runtime.task_id || "n/a")}
                            </p>
                            <p>
                              Runtime phase: {String(selectedDetail.latest_task_runtime.current_phase || "n/a")}
                            </p>
                            <p>
                              Runtime status: {String(selectedDetail.latest_task_runtime.status || "n/a")}
                            </p>
                          </>
                        ) : null}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-4">
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">Recent runs</h3>
                      <div className="mt-3 space-y-2">
                        {selectedDetail.runs.slice(0, 8).map((run) => (
                          <article
                            key={run.id}
                            className="rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] p-3 text-xs text-[var(--text-secondary)]"
                          >
                            <div className="flex flex-wrap items-center gap-2 text-[var(--text-primary)]">
                              <span>#{run.id}</span>
                              <span>{run.status}</span>
                              <span>{run.trigger_reason}</span>
                            </div>
                            <p className="mt-2">Trace: {run.trace_id || "n/a"}</p>
                            <p>Task: {run.task_id || "n/a"}</p>
                            <p>
                              Attempt: {run.attempt}/{run.max_attempts}
                            </p>
                            {run.error_message ? <p>Error: {run.error_message}</p> : null}
                            {run.summary_text ? <p>Summary: {run.summary_text}</p> : null}
                          </article>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-4">
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">Audit trail</h3>
                      <div className="mt-3 space-y-2">
                        {selectedDetail.events.slice(0, 10).map((event) => (
                          <article
                            key={event.id}
                            className="rounded-xl border border-[var(--border-subtle)] bg-[var(--field-bg)] p-3 text-xs text-[var(--text-secondary)]"
                          >
                            <div className="flex flex-wrap items-center gap-2 text-[var(--text-primary)]">
                              <span>{event.event_type}</span>
                              <span>{event.created_at || "n/a"}</span>
                            </div>
                            {event.reason ? <p className="mt-2">Reason: {event.reason}</p> : null}
                            {event.trace_id ? <p>Trace: {event.trace_id}</p> : null}
                            {event.status_from || event.status_to ? (
                              <p>
                                State: {event.status_from || "n/a"} → {event.status_to || "n/a"}
                              </p>
                            ) : null}
                          </article>
                        ))}
                      </div>
                    </div>
                  </section>
                </div>
              ) : (
                <div className="text-sm text-[var(--text-secondary)]">Select a job to inspect or edit it.</div>
              )}
            </PageSection>
          ) : null}
        </>
      )}
    </div>
  );
}
