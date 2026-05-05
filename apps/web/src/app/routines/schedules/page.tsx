"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Clock3, DatabaseZap, History, Plus } from "lucide-react";
import {
  CronTable,
  type ScheduleTableActionKey,
  type ScheduleTableActionState,
  type ScheduleTableActionStates,
} from "@/components/schedules/cron-table";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { RoutinesDataLoading } from "@/components/layout/route-loading";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { useAppI18n } from "@/hooks/use-app-i18n";
import {
  PageEmptyState,
  PageMetricStrip,
  PageMetricStripItem,
} from "@/components/ui/page-primitives";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/ui/inline-alert";
import {
  RoutineEditor,
  type RoutineFormPayload,
} from "@/components/routines/routine-editor";
import { useRoutinesContext } from "@/components/routines/routines-context";
import { ConfirmationDialog } from "@/components/control-plane/shared/confirmation-dialog";
import { Drawer } from "@/components/ui/drawer";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useToast } from "@/hooks/use-toast";
import { formatAgentSelectionLabel, resolveAgentSelection } from "@/lib/agent-selection";
import { fetchControlPlaneDashboardJsonAllowError } from "@/lib/control-plane-dashboard";
import type { CronJob, ScheduleDetail, ScheduleRun } from "@/lib/types";
import {
  cn,
  formatDateTime,
  formatDuration,
  formatRelativeTime,
  truncateText,
} from "@/lib/utils";

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

function getRoutineTitle(job: CronJob | null): string {
  if (!job) return "";
  const payloadName = typeof job.payload?.name === "string" ? job.payload.name.trim() : "";
  return job.summary?.trim() || payloadName || truncateText(job.command, 56);
}

function getRunActivityTimestamp(run: ScheduleRun): string | null {
  return run.completed_at || run.started_at || run.scheduled_for || run.next_attempt_at;
}

function getRunSortTime(run: ScheduleRun): number {
  const value = getRunActivityTimestamp(run);
  if (!value) return Number.NEGATIVE_INFINITY;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? Number.NEGATIVE_INFINITY : timestamp;
}

function runStatusTone(status: string | null | undefined): StatusDotTone {
  switch (status) {
    case "succeeded":
      return "success";
    case "failed":
    case "blocked":
      return "danger";
    case "queued":
      return "warning";
    case "running":
      return "info";
    case "retrying":
      return "retry";
    default:
      return "neutral";
  }
}

function formatRunStatus(status: string | null | undefined): string {
  return status ? status.replaceAll("_", " ") : "unknown";
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

function buildPatch(detail: ScheduleDetail, draft: ScheduleEditDraft, name: string) {
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

  if (name.trim()) {
    patch.summary = name.trim();
  }

  return patch;
}

function buildCreateBody(payload: RoutineFormPayload) {
  const jobType = "agent_query" as const;
  const innerPayload: Record<string, unknown> = {
    name: payload.name,
    query: payload.instructions,
    connectors: payload.connectors,
    read_only: payload.readOnly,
    allowed_paths: payload.allowedPaths,
  };
  return {
    job_type: jobType,
    trigger_type: payload.triggerType,
    schedule_expr: payload.scheduleExpr,
    timezone: payload.timezone || "UTC",
    payload: innerPayload,
    provider_preference: undefined,
    model_preference: payload.modelPreference ?? undefined,
    work_dir: undefined,
    notification_policy: { mode: payload.notificationMode },
    verification_policy: { mode: payload.verificationMode },
    session_id: `dashboard:${payload.agentId}`,
    auto_activate: true,
  };
}

function payloadToDraft(payload: RoutineFormPayload, current: ScheduleEditDraft | null): ScheduleEditDraft {
  return {
    triggerType: payload.triggerType,
    scheduleExpr: payload.scheduleExpr,
    timezone: payload.timezone,
    content: payload.instructions,
    description: current?.description ?? "",
    workDir: current?.workDir ?? "",
    provider: current?.provider ?? "",
    model: payload.modelPreference ?? "",
    notificationMode: payload.notificationMode,
    verificationMode: payload.verificationMode,
  };
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
  const [busyJobId, setBusyJobId] = useState<number | null>(null);
  const [tableActionStates, setTableActionStates] = useState<ScheduleTableActionStates>({});
  const [executionDrawerJob, setExecutionDrawerJob] = useState<CronJob | null>(null);
  const [executionDrawerDetail, setExecutionDrawerDetail] = useState<ScheduleDetail | null>(null);
  const [executionDrawerLoading, setExecutionDrawerLoading] = useState(false);
  const [executionDrawerError, setExecutionDrawerError] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<ScheduleEditDraft | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [creatingRoutine, setCreatingRoutine] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [pendingDeleteJob, setPendingDeleteJob] = useState<CronJob | null>(null);
  const { defaultTimezone } = useRoutinesContext();
  const { showToast } = useToast();
  const idempotencyKeyRef = useRef<string>("");
  const tableActionClearTimersRef = useRef<Record<string, number>>({});

  useEffect(() => {
    if (creatingRoutine && !idempotencyKeyRef.current) {
      idempotencyKeyRef.current =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `routine-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }
    if (!creatingRoutine) {
      idempotencyKeyRef.current = "";
    }
  }, [creatingRoutine]);

  useEffect(
    () => () => {
      Object.values(tableActionClearTimersRef.current).forEach((timerId) => {
        window.clearTimeout(timerId);
      });
    },
    [],
  );

  function setTableActionState(
    jobId: number,
    actionKey: ScheduleTableActionKey | undefined,
    state: ScheduleTableActionState,
  ) {
    if (!actionKey) return;

    const stateKey = `${jobId}:${actionKey}`;
    const existingTimer = tableActionClearTimersRef.current[stateKey];
    if (existingTimer) {
      window.clearTimeout(existingTimer);
      delete tableActionClearTimersRef.current[stateKey];
    }

    setTableActionStates((current) => ({
      ...current,
      [jobId]: {
        ...current[jobId],
        [actionKey]: state,
      },
    }));

    if (state === "success" || state === "error") {
      tableActionClearTimersRef.current[stateKey] = window.setTimeout(() => {
        setTableActionStates((current) => {
          const currentJob = current[jobId];
          if (!currentJob || currentJob[actionKey] !== state) return current;

          const nextJob = { ...currentJob };
          delete nextJob[actionKey];

          const next = { ...current };
          if (Object.keys(nextJob).length === 0) {
            delete next[jobId];
          } else {
            next[jobId] = nextJob;
          }
          return next;
        });
        delete tableActionClearTimersRef.current[stateKey];
      }, 1400);
    }
  }

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

  async function loadDetail(job: CronJob, actionKey?: ScheduleTableActionKey) {
    if (!job.bot_id) return;
    setTableActionState(job.id, actionKey, "pending");
    setSelectedJob(job);
    setEditorError(null);
    try {
      const response = await fetch(`/api/runtime/agents/${job.bot_id}/schedules/${job.id}`, {
        cache: "no-store",
      });
      const payload = (await response.json()) as ScheduleDetail | { error?: string };
      if (!response.ok) {
        throw new Error(
          "error" in payload ? payload.error || "Unable to load schedule" : "Unable to load schedule",
        );
      }
      const detail = payload as ScheduleDetail;
      setSelectedDetail(detail);
      setEditDraft(buildDraft(detail));
      setTableActionState(job.id, actionKey, "success");
    } catch (error) {
      setEditorError(error instanceof Error ? error.message : "Unable to load schedule detail");
      setSelectedDetail(null);
      setEditDraft(null);
      setTableActionState(job.id, actionKey, "error");
    }
  }

  async function loadExecutionHistory(job: CronJob) {
    if (!job.bot_id) return;
    setExecutionDrawerJob(job);
    setExecutionDrawerDetail(null);
    setExecutionDrawerError(null);
    setExecutionDrawerLoading(true);
    setTableActionState(job.id, "executions", "pending");
    try {
      const response = await fetch(`/api/runtime/agents/${job.bot_id}/schedules/${job.id}`, {
        cache: "no-store",
      });
      const payload = (await response.json()) as ScheduleDetail | { error?: string };
      if (!response.ok) {
        throw new Error(
          "error" in payload
            ? payload.error || "Unable to load schedule executions"
            : "Unable to load schedule executions",
        );
      }
      setExecutionDrawerDetail(payload as ScheduleDetail);
      setTableActionState(job.id, "executions", "success");
    } catch (error) {
      setExecutionDrawerError(
        error instanceof Error ? error.message : "Unable to load schedule executions",
      );
      setTableActionState(job.id, "executions", "error");
    } finally {
      setExecutionDrawerLoading(false);
    }
  }

  async function runAction(
    job: CronJob,
    action: "pause" | "resume" | "run" | "validate" | "delete",
    actionKey?: ScheduleTableActionKey,
  ) {
    if (!job.bot_id) return;
    setBusyJobId(job.id);
    setTableActionState(job.id, actionKey, "pending");
    setStatusMessage(null);
    setEditorError(null);
    try {
      const response = await fetch(
        `/api/runtime/agents/${job.bot_id}/schedules/${job.id}/actions/${action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: job.user_id }),
        },
      );
      const payload = (await response.json()) as
        | ({ message?: string } & Partial<ScheduleDetail>)
        | { error?: string };
      if (!response.ok) {
        throw new Error(
          "error" in payload
            ? payload.error || "Unable to operate on schedule"
            : "Unable to operate on schedule",
        );
      }
      setStatusMessage((payload as { message?: string }).message || "Schedule updated.");
      setTableActionState(job.id, actionKey, "success");
      if (action === "delete") {
        setSelectedJob(null);
        setSelectedDetail(null);
        setEditDraft(null);
      } else if ("job" in payload && payload.job) {
        setSelectedDetail(payload as ScheduleDetail);
        setSelectedJob((payload as ScheduleDetail).job);
        setEditDraft(buildDraft(payload as ScheduleDetail));
      } else {
        await loadDetail(job);
      }
      setRefreshNonce((value) => value + 1);
    } catch (error) {
      setEditorError(error instanceof Error ? error.message : "Unable to operate on schedule");
      setTableActionState(job.id, actionKey, "error");
    } finally {
      setBusyJobId(null);
    }
  }

  async function applySchedulePayload(payload: RoutineFormPayload) {
    if (creatingRoutine) {
      const targetAgentId = payload.agentId || agents[0]?.id;
      if (!targetAgentId) {
        setEditorError(t("routines.editor.errors.unauthorized"));
        return;
      }
      setBusyJobId(-1);
      setStatusMessage(null);
      setEditorError(null);
      try {
        const body = buildCreateBody(payload);
        const response = await fetch(`/api/runtime/agents/${targetAgentId}/schedules`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Idempotency-Key": idempotencyKeyRef.current,
          },
          body: JSON.stringify(body),
        });
        const responseBody = (await response.json()) as
          | ({ ok?: boolean; idempotent_replay?: boolean } & Partial<ScheduleDetail>)
          | { error?: string; field?: string };
        if (!response.ok) {
          const fallback = t("routines.editor.messages.createFailed");
          const errMessage =
            "error" in responseBody ? responseBody.error || fallback : fallback;
          showToast(errMessage, "error");
          throw new Error(errMessage);
        }
        showToast(t("routines.editor.messages.created"), "success");
        setStatusMessage(t("routines.editor.messages.created"));
        setCreatingRoutine(false);
        setRefreshNonce((value) => value + 1);
      } catch (error) {
        setEditorError(
          error instanceof Error ? error.message : t("routines.editor.messages.createFailed"),
        );
      } finally {
        setBusyJobId(null);
      }
      return;
    }

    if (!selectedJob?.bot_id || !selectedDetail) return;
    const draft = payloadToDraft(payload, editDraft);
    setEditDraft(draft);
    setBusyJobId(selectedJob.id);
    setStatusMessage(null);
    setEditorError(null);
    try {
      const response = await fetch(
        `/api/runtime/agents/${selectedJob.bot_id}/schedules/${selectedJob.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: selectedDetail.job.user_id,
            expected_config_version: selectedDetail.job.config_version,
            reason: t("schedules.inspector.messages.updateReason"),
            patch: buildPatch(selectedDetail, draft, payload.name),
          }),
        },
      );
      const responseBody = (await response.json()) as
        | ({ message?: string } & Partial<ScheduleDetail>)
        | { error?: string };
      if (!response.ok) {
        if (response.status === 409 && selectedJob) {
          showToast(t("routines.editor.errors.conflict"), "error");
          await loadDetail(selectedJob);
          setEditorError(t("routines.editor.errors.conflict"));
          return;
        }
        const fallback = t("schedules.inspector.messages.updateFailed");
        throw new Error(
          "error" in responseBody ? responseBody.error || fallback : fallback,
        );
      }
      showToast(t("routines.editor.messages.updated"), "success");
      setStatusMessage(
        (responseBody as { message?: string }).message || t("schedules.inspector.messages.updated"),
      );
      if ("job" in responseBody && responseBody.job) {
        setSelectedDetail(responseBody as ScheduleDetail);
        setSelectedJob((responseBody as ScheduleDetail).job);
        setEditDraft(buildDraft(responseBody as ScheduleDetail));
      }
      setRefreshNonce((value) => value + 1);
      setSelectedJob(null);
      setSelectedDetail(null);
      setEditDraft(null);
    } catch (error) {
      setEditorError(
        error instanceof Error ? error.message : t("schedules.inspector.messages.updateFailed"),
      );
    } finally {
      setBusyJobId(null);
    }
  }

  const visibleAgents = useMemo(
    () =>
      agents
        .filter((agent) => visibleBotIds.includes(agent.id))
        .map((agent) => ({
          agent,
          jobs: jobsByAgent[agent.id] || [],
        })),
    [agents, jobsByAgent, visibleBotIds],
  );
  const scheduleRows = useMemo(
    () =>
      visibleAgents.flatMap((entry) =>
        entry.jobs.map((job) => ({
          job,
          agent: entry.agent,
        })),
      ),
    [visibleAgents],
  );

  const totalJobs = visibleAgents.reduce((sum, entry) => sum + entry.jobs.length, 0);
  const enabledJobs = visibleAgents.reduce(
    (sum, entry) => sum + entry.jobs.filter((job) => job.enabled === 1).length,
    0,
  );
  const disabledJobs = totalJobs - enabledJobs;
  const botsWithJobs = visibleAgents.filter((entry) => entry.jobs.length > 0);

  const editorOpen = creatingRoutine || Boolean(selectedJob);
  const editorMode: "create" | "edit" = creatingRoutine ? "create" : "edit";

  function closeEditor() {
    setCreatingRoutine(false);
    setSelectedJob(null);
    setSelectedDetail(null);
    setEditDraft(null);
    setEditorError(null);
  }

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
        <div className="md:ml-auto">
          <Button
            type="button"
            variant="accent"
            size="md"
            onClick={() => {
              setCreatingRoutine(true);
              setSelectedJob(null);
              setSelectedDetail(null);
              setEditDraft(null);
              setEditorError(null);
            }}
            disabled={agents.length === 0}
          >
            <Plus className="icon-sm" strokeWidth={1.75} aria-hidden />
            {t("routines.editor.actions.newRoutine")}
          </Button>
        </div>
      </div>

      {statusMessage ? (
        <InlineAlert tone="info">{statusMessage}</InlineAlert>
      ) : null}

      {loading ? (
        <RoutinesDataLoading />
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
                actions={
                  <Button
                    type="button"
                    variant="accent"
                    size="md"
                    onClick={() => {
                      setCreatingRoutine(true);
                      setSelectedJob(null);
                      setSelectedDetail(null);
                      setEditDraft(null);
                      setEditorError(null);
                    }}
                    disabled={agents.length === 0}
                  >
                    <Plus className="icon-sm" strokeWidth={1.75} aria-hidden />
                    {t("routines.editor.actions.createFirst")}
                  </Button>
                }
              />
            </div>
          ) : (
            <section className="animate-in stagger-2">
              <CronTable
                rows={scheduleRows}
                busyJobId={busyJobId}
                actionStates={tableActionStates}
                onInspect={(job) => void loadDetail(job, "inspect")}
                onEdit={(job) => void loadDetail(job, "edit")}
                onExecutions={(job) => void loadExecutionHistory(job)}
                onRun={(job) => void runAction(job, "run", "run")}
                onLifecycleAction={(job, action) => void runAction(job, action, "lifecycle")}
              />
            </section>
          )}
        </>
      )}

      <RoutineEditor
        open={editorOpen}
        onOpenChange={(open) => {
          if (!open) closeEditor();
        }}
        mode={editorMode}
        job={editorMode === "edit" ? selectedJob : null}
        detail={editorMode === "edit" ? selectedDetail : null}
        agents={agents}
        defaultAgentId={visibleBotIds[0] ?? agents[0]?.id}
        defaultTimezone={defaultTimezone}
        busy={busyJobId !== null}
        errorMessage={editorError}
        onSubmit={applySchedulePayload}
        onDelete={
          editorMode === "edit" && selectedJob
            ? () => setPendingDeleteJob(selectedJob)
            : undefined
        }
      />

      <RoutineExecutionsDrawer
        open={Boolean(executionDrawerJob)}
        job={executionDrawerJob}
        detail={executionDrawerDetail}
        loading={executionDrawerLoading}
        error={executionDrawerError}
        onOpenChange={(open) => {
          if (!open) {
            setExecutionDrawerJob(null);
            setExecutionDrawerDetail(null);
            setExecutionDrawerError(null);
            setExecutionDrawerLoading(false);
          }
        }}
      />

      <ConfirmationDialog
        open={Boolean(pendingDeleteJob)}
        title={t("routines.editor.delete.confirmTitle")}
        message={t("routines.editor.delete.confirmDescription")}
        confirmLabel={t("routines.editor.delete.confirmAction")}
        onCancel={() => setPendingDeleteJob(null)}
        onConfirm={async () => {
          const job = pendingDeleteJob;
          setPendingDeleteJob(null);
          if (!job) return;
          await runAction(job, "delete");
          showToast(t("routines.editor.messages.deleted"), "success");
          closeEditor();
        }}
      />
    </div>
  );
}

function RoutineExecutionsDrawer({
  open,
  job,
  detail,
  loading,
  error,
  onOpenChange,
}: {
  open: boolean;
  job: CronJob | null;
  detail: ScheduleDetail | null;
  loading: boolean;
  error: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useAppI18n();
  const runs = useMemo(
    () =>
      [...(detail?.runs ?? [])].sort(
        (left, right) => getRunSortTime(right) - getRunSortTime(left) || right.id - left.id,
      ),
    [detail?.runs],
  );
  const title = t("schedules.executions.title", {
    defaultValue: "Routine executions",
  });
  const routineTitle = getRoutineTitle(job);

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title={
        <span className="inline-flex min-w-0 items-center gap-2">
          <History className="icon-sm shrink-0 text-[var(--text-quaternary)]" strokeWidth={1.75} />
          <span className="truncate">{title}</span>
        </span>
      }
      description={routineTitle || t("schedules.inspector.detailFallback")}
      width="min(620px, 94vw)"
      closeLabel={t("common.close", { defaultValue: "Close" })}
    >
      <div className="px-5 py-5">
        {loading ? (
          <div className="space-y-3" aria-label={t("common.loading", { defaultValue: "Loading" })}>
            {Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className="rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] px-4 py-3"
              >
                <div className="skeleton-shimmer h-3 w-28 rounded-full" />
                <div className="skeleton-shimmer mt-3 h-4 w-3/4 rounded-full" />
                <div className="mt-3 flex gap-2">
                  <div className="skeleton-shimmer h-3 w-20 rounded-full" />
                  <div className="skeleton-shimmer h-3 w-24 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <InlineAlert tone="danger">{error}</InlineAlert>
        ) : runs.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <History
              className="icon-lg text-[var(--text-quaternary)]"
              strokeWidth={1.5}
              aria-hidden
            />
            <p className="m-0 text-[var(--font-size-sm)] font-medium text-[var(--text-primary)]">
              {t("schedules.executions.empty", { defaultValue: "No executions yet." })}
            </p>
            <p className="m-0 max-w-[32rem] text-[0.75rem] leading-[1.5] text-[var(--text-tertiary)]">
              {t("schedules.executions.emptyDescription", {
                defaultValue: "When this routine runs, the most recent records appear here first.",
              })}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => (
              <RoutineExecutionRow key={run.id} run={run} />
            ))}
          </div>
        )}
      </div>
    </Drawer>
  );
}

function RoutineExecutionRow({ run }: { run: ScheduleRun }) {
  const { t } = useAppI18n();
  const activityAt = getRunActivityTimestamp(run);
  const status = formatRunStatus(run.status);
  const primaryText = run.summary_text?.trim() || run.error_message?.trim();

  return (
    <article className="rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel)] px-4 py-3">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              #{run.id}
            </span>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border px-2 py-0.5 text-[0.6875rem] font-medium uppercase tracking-[var(--tracking-mono)]",
                "border-[color:var(--border-subtle)] text-[var(--text-secondary)]",
              )}
            >
              <StatusDot tone={runStatusTone(run.status)} pulse={run.status === "running"} />
              {status}
            </span>
          </div>
          <p
            className="m-0 mt-2 line-clamp-2 text-[0.8125rem] leading-[1.5] text-[var(--text-primary)]"
            title={primaryText || undefined}
          >
            {primaryText || t("schedules.executions.noSummary", { defaultValue: "No summary recorded." })}
          </p>
        </div>
        <time
          className="shrink-0 whitespace-nowrap text-right font-mono text-[0.6875rem] text-[var(--text-quaternary)]"
          title={formatDateTime(activityAt)}
        >
          {formatRelativeTime(activityAt)}
        </time>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)] sm:grid-cols-4">
        <RunMeta label={t("schedules.inspector.runtimeTask")} value={run.task_id ? `#${run.task_id}` : "—"} />
        <RunMeta label={t("common.duration", { defaultValue: "Duration" })} value={formatDuration(run.duration_ms)} />
        <RunMeta label={t("common.attempts", { defaultValue: "Attempts" })} value={`${run.attempt}/${run.max_attempts}`} />
        <RunMeta label={t("common.model", { defaultValue: "Model" })} value={run.model_effective || "—"} />
      </div>
    </article>
  );
}

function RunMeta({ label, value }: { label: string; value: string }) {
  return (
    <span className="min-w-0">
      <span className="block truncate uppercase tracking-[var(--tracking-mono)]">{label}</span>
      <span className="mt-0.5 block truncate text-[var(--text-secondary)]" title={value}>
        {value}
      </span>
    </span>
  );
}
