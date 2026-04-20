"use client";

import { useEffect, useMemo, useState } from "react";
import { Clock3, DatabaseZap } from "lucide-react";
import { CronTable } from "@/components/schedules/cron-table";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  PageEmptyState,
  PageMetricStrip,
  PageMetricStripItem,
  PageSection,
  PageSectionHeader,
} from "@/components/ui/page-primitives";
import { InlineAlert } from "@/components/ui/inline-alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatusDot } from "@/components/ui/status-dot";
import { formatAgentSelectionLabel, resolveAgentSelection } from "@/lib/agent-selection";
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

function getLifecycleLabelKey(job: CronJob | null): string {
  if (!job) {
    return "schedules.inspector.lifecycle.update";
  }
  switch (job.status) {
    case "active":
      return "schedules.inspector.lifecycle.pause";
    case "paused":
      return "schedules.inspector.lifecycle.resume";
    case "validated":
      return "schedules.inspector.lifecycle.activate";
    case "failed_open":
      return "schedules.inspector.lifecycle.resumeFailedOpen";
    case "validation_pending":
      return "schedules.inspector.lifecycle.queueValidation";
    default:
      return job.enabled === 1
        ? "schedules.inspector.lifecycle.pause"
        : "schedules.inspector.lifecycle.activateOrResume";
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
  const { agents } = useAgentCatalog();
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [jobsByAgent, setJobsByAgent] = useState<Record<string, CronJob[]>>({});
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
  const availableBotIds = useMemo(() => agents.map((agent) => agent.id), [agents]);
  const visibleBotIds = useMemo(
    () => resolveAgentSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const selectionLabel = formatAgentSelectionLabel(visibleBotIds, agents);

  useEffect(() => {
    async function fetchSchedules() {
      setLoading(true);
      setUnavailable(false);
      try {
        const response = await fetchControlPlaneDashboardJsonAllowError<CronJob[]>("/schedules", {
          params: { agent: visibleBotIds },
          fallbackError: t("schedules.page.unavailableDescription", {
            defaultValue: "Unable to load canonical schedules.",
          }),
        });

        const results: Record<string, CronJob[]> = {};
        for (const agent of agents) {
          results[agent.id] = [];
        }

        for (const job of Array.isArray(response.data) ? response.data : []) {
          if (!job.bot_id || !results[job.bot_id]) {
            continue;
          }
          results[job.bot_id].push(job);
        }

        setJobsByAgent(results);
        setUnavailable(!response.ok);
      } catch {
        setJobsByAgent({});
        setUnavailable(true);
      } finally {
        setLoading(false);
      }
    }

    void fetchSchedules();
  }, [agents, t, visibleBotIds, refreshNonce]);

  async function loadDetail(job: CronJob) {
    if (!job.bot_id) return;
    setSelectedJob(job);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const response = await fetch(`/api/runtime/agents/${job.bot_id}/schedules/${job.id}`, {
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
      const response = await fetch(`/api/runtime/agents/${job.bot_id}/schedules/${job.id}/actions/${action}`, {
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
      const response = await fetch(`/api/runtime/agents/${selectedJob.bot_id}/schedules/${selectedJob.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: selectedDetail.job.user_id,
          expected_config_version: selectedDetail.job.config_version,
          reason: t("schedules.inspector.messages.updateReason"),
          patch: buildPatch(selectedDetail, editDraft),
        }),
      });
      const payload = (await response.json()) as
        | ({ message?: string } & Partial<ScheduleDetail>)
        | { error?: string };
      if (!response.ok) {
        const fallback = t("schedules.inspector.messages.updateFailed");
        throw new Error("error" in payload ? payload.error || fallback : fallback);
      }
      setStatusMessage((payload as { message?: string }).message || t("schedules.inspector.messages.updated"));
      if ("job" in payload && payload.job) {
        setSelectedDetail(payload as ScheduleDetail);
        setSelectedJob((payload as ScheduleDetail).job);
        setEditDraft(buildDraft(payload as ScheduleDetail));
      }
      setRefreshNonce((value) => value + 1);
    } catch (error) {
      setStatusMessage(
        error instanceof Error ? error.message : t("schedules.inspector.messages.updateFailed"),
      );
    } finally {
      setBusyJobId(null);
    }
  }

  const visibleAgents = useMemo(
    () =>
      agents.filter((agent) => visibleBotIds.includes(agent.id)).map((agent) => ({
        agent,
        jobs: jobsByAgent[agent.id] || [],
      })),
    [agents, jobsByAgent, visibleBotIds]
  );

  const totalJobs = visibleAgents.reduce((sum, entry) => sum + entry.jobs.length, 0);
  const enabledJobs = visibleAgents.reduce(
    (sum, entry) => sum + entry.jobs.filter((job) => job.enabled === 1).length,
    0
  );
  const disabledJobs = totalJobs - enabledJobs;
  const botsWithJobs = visibleAgents.filter((entry) => entry.jobs.length > 0);

  return (
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
      </div>

      {statusMessage ? (
        <InlineAlert tone="info">{statusMessage}</InlineAlert>
      ) : null}

      {loading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className="flex h-[72px] animate-pulse flex-col gap-2 rounded-[var(--radius-panel-sm)] bg-[var(--panel-soft)] p-4"
              >
                <div className="h-3 w-16 rounded bg-[var(--panel-strong)]" />
                <div className="h-5 w-12 rounded bg-[var(--panel-strong)]" />
              </div>
            ))}
          </div>
          <div className="min-h-[400px]" />
        </div>
      ) : (
        <>
          <PageMetricStrip className="animate-in stagger-1">
            <PageMetricStripItem
              label={t("schedules.page.visibleAgents")}
              value={`${visibleAgents.length}`}
              hint={selectionLabel}
            />
            <PageMetricStripItem
              label={t("schedules.page.withSchedule")}
              value={`${botsWithJobs.length}`}
              hint={t("schedules.page.withAtLeastOne")}
            />
            <PageMetricStripItem
              label={t("schedules.page.enabled")}
              value={`${enabledJobs}`}
              hint={t("schedules.page.runningNormally")}
            />
            <PageMetricStripItem
              label={t("schedules.page.paused")}
              value={`${disabledJobs}`}
              hint={t("schedules.page.registeredDisabled")}
            />
          </PageMetricStrip>

          {unavailable ? (
            <div className="animate-in stagger-2 py-6">
              <PageEmptyState
                icon={DatabaseZap}
                title={t("schedules.page.unavailable", {
                  defaultValue: "Canonical scheduler data unavailable",
                })}
                description={t("schedules.page.unavailableDescription", {
                  defaultValue:
                    "The control-plane/runtime APIs do not expose per-agent cron inventory in this deployment.",
                })}
              />
            </div>
          ) : botsWithJobs.length === 0 ? (
            <div className="animate-in stagger-2 py-6">
              <PageEmptyState
                icon={Clock3}
                title={t("schedules.page.noVisible")}
                description={t("schedules.page.noVisibleDescription")}
              />
            </div>
          ) : (
            <section
              className={`animate-in stagger-2 grid gap-4 ${
                botsWithJobs.length > 1 ? "xl:grid-cols-2" : "grid-cols-1"
              }`}
            >
              {botsWithJobs.map((entry) => {
                return (
                  <div key={entry.agent.id} className="flex flex-col gap-3">
                    <header className="flex items-baseline justify-between px-1">
                      <span className="font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                        {entry.agent.label}
                      </span>
                      <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                        {t("schedules.page.configured", {
                          count: entry.jobs.length,
                          defaultValue: "{{count}} configured",
                        })}
                      </span>
                    </header>

                    <CronTable
                      jobs={entry.jobs}
                      agentLabel={entry.agent.label}
                      agentColor={entry.agent.color}
                      busyJobId={busyJobId}
                      onInspect={(job) => void loadDetail(job)}
                      onEdit={(job) => void loadDetail(job)}
                      onRun={(job) => void runAction(job, "run")}
                      onLifecycleAction={(job, action) => void runAction(job, action)}
                    />
                  </div>
                );
              })}
            </section>
          )}

          {selectedJob ? (
            <PageSection className="animate-in stagger-3 px-5 py-5 lg:px-6">
              <PageSectionHeader
                eyebrow={t("schedules.inspector.eyebrow")}
                title={t("schedules.inspector.jobTitle", { id: selectedJob.id })}
                description={
                  selectedJob.summary ||
                  selectedJob.command ||
                  t("schedules.inspector.detailFallback")
                }
              />

              {detailLoading ? (
                <div className="text-sm text-[var(--text-secondary)]">{t("schedules.inspector.loadingDetail")}</div>
              ) : detailError ? (
                <div className="text-sm text-[var(--text-secondary)]">{detailError}</div>
              ) : selectedDetail && editDraft ? (
                <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
                  <section className="flex flex-col gap-4">
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="text-sm text-[var(--text-secondary)]">
                        {t("schedules.inspector.trigger")}
                        <div className="mt-1">
                          <Select
                            value={editDraft.triggerType}
                            onValueChange={(v) =>
                              setEditDraft((current) =>
                                current ? { ...current, triggerType: v } : current,
                              )
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="one_shot">{t("schedules.inspector.triggerTypes.one_shot")}</SelectItem>
                              <SelectItem value="interval">{t("schedules.inspector.triggerTypes.interval")}</SelectItem>
                              <SelectItem value="cron">{t("schedules.inspector.triggerTypes.cron")}</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </label>
                      <label className="text-sm text-[var(--text-secondary)]">
                        {t("schedules.inspector.timezone")}
                        <input
                          className="field-shell mt-1 text-[var(--text-primary)]"
                          value={editDraft.timezone}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current ? { ...current, timezone: event.target.value } : current
                            )
                          }
                        />
                      </label>
                      <label className="text-sm text-[var(--text-secondary)] md:col-span-2">
                        {t("schedules.inspector.scheduleExpression")}
                        <input
                          className="field-shell mt-1 text-[var(--text-primary)]"
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
                          ? t("schedules.inspector.reminderText")
                          : selectedDetail.job.job_type === "shell_command"
                            ? t("schedules.inspector.command")
                            : t("schedules.inspector.query")}
                        <textarea
                          className="field-shell mt-1 min-h-[120px] text-[var(--text-primary)]"
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
                          {t("schedules.inspector.description")}
                          <input
                            className="field-shell mt-1 text-[var(--text-primary)]"
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
                        {t("schedules.inspector.workDir")}
                        <input
                          className="field-shell mt-1 text-[var(--text-primary)]"
                          value={editDraft.workDir}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current ? { ...current, workDir: event.target.value } : current
                            )
                          }
                        />
                      </label>
                      <label className="text-sm text-[var(--text-secondary)]">
                        {t("schedules.inspector.notificationMode")}
                        <div className="mt-1">
                          <Select
                            value={editDraft.notificationMode}
                            onValueChange={(v) =>
                              setEditDraft((current) =>
                                current ? { ...current, notificationMode: v } : current,
                              )
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="summary_complete">summary_complete</SelectItem>
                              <SelectItem value="failures_only">failures_only</SelectItem>
                              <SelectItem value="none">none</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </label>
                      <label className="text-sm text-[var(--text-secondary)]">
                        {t("schedules.inspector.verificationMode")}
                        <div className="mt-1">
                          <Select
                            value={editDraft.verificationMode}
                            onValueChange={(v) =>
                              setEditDraft((current) =>
                                current ? { ...current, verificationMode: v } : current,
                              )
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="post_write_if_any">post_write_if_any</SelectItem>
                              <SelectItem value="task_success">task_success</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </label>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                        onClick={() => void saveEdit()}
                        disabled={busyJobId === selectedJob.id}
                      >
                        {t("schedules.inspector.actions.saveChanges")}
                      </button>
                      <button
                        type="button"
                        className="rounded-xl border border-[var(--border-subtle)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)]"
                        onClick={() => void runAction(selectedJob, "validate")}
                        disabled={busyJobId === selectedJob.id}
                      >
                        {t("schedules.inspector.actions.queueValidation")}
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
                        {t(getLifecycleLabelKey(selectedDetail.job))}
                      </button>
                      <button
                        type="button"
                        className="rounded-xl border border-[var(--border-subtle)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)]"
                        onClick={() => void runAction(selectedJob, "delete")}
                        disabled={busyJobId === selectedJob.id}
                      >
                        {t("schedules.inspector.actions.archiveJob")}
                      </button>
                      <button
                        type="button"
                        className="rounded-xl border border-[var(--border-subtle)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)]"
                        onClick={() => void loadDetail(selectedJob)}
                        disabled={busyJobId === selectedJob.id}
                      >
                        {t("schedules.inspector.actions.refreshDetail")}
                      </button>
                    </div>
                  </section>

                  <section className="flex flex-col divide-y divide-[color:var(--divider-hair)]">
                    <div className="pb-5">
                      <h3 className="m-0 mb-3 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                        {t("schedules.inspector.currentStatus")}
                      </h3>
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[0.8125rem]">
                        <dt className="text-[var(--text-quaternary)]">{t("schedules.inspector.status")}</dt>
                        <dd className="m-0 inline-flex items-center gap-1.5 text-[var(--text-primary)]">
                          <StatusDot
                            tone={
                              selectedDetail.job.status === "active"
                                ? "success"
                                : selectedDetail.job.status === "failed_open"
                                  ? "danger"
                                  : selectedDetail.job.status === "validation_pending"
                                    ? "warning"
                                    : "neutral"
                            }
                            pulse={selectedDetail.job.status === "active"}
                          />
                          {selectedDetail.job.status || t("schedules.inspector.unknown")}
                        </dd>
                        <dt className="text-[var(--text-quaternary)]">{t("schedules.inspector.nextRun")}</dt>
                        <dd className="m-0 truncate font-mono text-[var(--text-primary)]">
                          {selectedDetail.job.next_run_at || t("schedules.inspector.pendingValidation")}
                        </dd>
                        <dt className="text-[var(--text-quaternary)]">{t("schedules.inspector.version")}</dt>
                        <dd className="m-0 font-mono text-[var(--text-primary)]">
                          {selectedDetail.job.config_version || 1}
                        </dd>
                        {selectedDetail.latest_task_runtime ? (
                          <>
                            <dt className="text-[var(--text-quaternary)]">{t("schedules.inspector.runtimeTask")}</dt>
                            <dd className="m-0 font-mono text-[var(--text-primary)]">
                              {String(selectedDetail.latest_task_runtime.task_id || "—")}
                            </dd>
                            <dt className="text-[var(--text-quaternary)]">{t("schedules.inspector.phase")}</dt>
                            <dd className="m-0 font-mono text-[var(--text-primary)]">
                              {String(selectedDetail.latest_task_runtime.current_phase || "—")}
                            </dd>
                          </>
                        ) : null}
                      </dl>
                    </div>

                    <div className="py-5">
                      <h3 className="m-0 mb-2 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                        {t("schedules.inspector.recentRuns")}
                      </h3>
                      <ol className="flex flex-col">
                        {selectedDetail.runs.slice(0, 8).map((run) => {
                          const runTone =
                            run.status === "completed" || run.status === "success"
                              ? "success"
                              : run.status === "failed"
                                ? "danger"
                                : run.status === "running"
                                  ? "info"
                                  : "neutral";
                          return (
                            <li
                              key={run.id}
                              className="grid grid-cols-[auto_1fr_auto] items-start gap-3 border-b border-[color:var(--divider-hair)] py-2.5 last:border-b-0"
                            >
                              <StatusDot tone={runTone} pulse={run.status === "running"} />
                              <div className="min-w-0">
                                <p className="m-0 truncate text-[0.8125rem] text-[var(--text-secondary)]">
                                  <span className="font-mono text-[var(--text-quaternary)]">
                                    #{run.id}
                                  </span>
                                  {run.trigger_reason ? (
                                    <> · <span>{run.trigger_reason}</span></>
                                  ) : null}
                                </p>
                                {run.error_message ? (
                                  <p className="m-0 truncate text-[0.6875rem] text-[var(--tone-danger-dot)]">
                                    {run.error_message}
                                  </p>
                                ) : run.summary_text ? (
                                  <p className="m-0 truncate text-[0.6875rem] text-[var(--text-quaternary)]">
                                    {run.summary_text}
                                  </p>
                                ) : null}
                              </div>
                              <span className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                                {run.attempt}/{run.max_attempts}
                              </span>
                            </li>
                          );
                        })}
                        {selectedDetail.runs.length === 0 ? (
                          <li className="py-2.5 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
                            {t("schedules.inspector.noRunsYet")}
                          </li>
                        ) : null}
                      </ol>
                    </div>

                    <div className="py-5">
                      <h3 className="m-0 mb-2 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
                        {t("schedules.inspector.auditTrail")}
                      </h3>
                      <ol className="flex flex-col">
                        {selectedDetail.events.slice(0, 10).map((event) => (
                          <li
                            key={event.id}
                            className="grid grid-cols-[1fr_auto] items-start gap-3 border-b border-[color:var(--divider-hair)] py-2.5 last:border-b-0"
                          >
                            <div className="min-w-0">
                              <p className="m-0 truncate text-[0.8125rem] text-[var(--text-secondary)]">
                                {event.event_type}
                                {event.status_from || event.status_to ? (
                                  <>
                                    {" · "}
                                    <span className="font-mono text-[var(--text-quaternary)]">
                                      {event.status_from || "—"} → {event.status_to || "—"}
                                    </span>
                                  </>
                                ) : null}
                              </p>
                              {event.reason ? (
                                <p className="m-0 truncate text-[0.6875rem] text-[var(--text-quaternary)]">
                                  {event.reason}
                                </p>
                              ) : null}
                            </div>
                            <span className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                              {event.created_at || "—"}
                            </span>
                          </li>
                        ))}
                        {selectedDetail.events.length === 0 ? (
                          <li className="py-2.5 text-[var(--font-size-sm)] text-[var(--text-tertiary)]">
                            {t("schedules.inspector.noEventsYet")}
                          </li>
                        ) : null}
                      </ol>
                    </div>
                  </section>
                </div>
              ) : (
                <div className="text-sm text-[var(--text-secondary)]">{t("schedules.inspector.selectToInspect")}</div>
              )}
            </PageSection>
          ) : null}
        </>
      )}
    </div>
  );
}
