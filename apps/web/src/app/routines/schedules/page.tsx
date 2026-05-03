"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Clock3, DatabaseZap, Plus } from "lucide-react";
import { CronTable } from "@/components/schedules/cron-table";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
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
import { useToast } from "@/hooks/use-toast";
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
  const [editDraft, setEditDraft] = useState<ScheduleEditDraft | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [creatingRoutine, setCreatingRoutine] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [pendingDeleteJob, setPendingDeleteJob] = useState<CronJob | null>(null);
  const { defaultTimezone } = useRoutinesContext();
  const { showToast } = useToast();
  const idempotencyKeyRef = useRef<string>("");

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
    } catch (error) {
      setEditorError(error instanceof Error ? error.message : "Unable to load schedule detail");
      setSelectedDetail(null);
      setEditDraft(null);
    }
  }

  async function runAction(job: CronJob, action: "pause" | "resume" | "run" | "validate" | "delete") {
    if (!job.bot_id) return;
    setBusyJobId(job.id);
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
