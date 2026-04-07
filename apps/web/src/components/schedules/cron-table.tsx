"use client";

import { Clock, FolderTree, Pencil, Play, TerminalSquare } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { CronJob } from "@/lib/types";
import { getSemanticDotStyle, getSemanticStyle } from "@/lib/theme-semantic";
import { truncateText } from "@/lib/utils";

type ScheduleLifecycleAction = "pause" | "resume" | "validate";

interface CronTableProps {
  jobs: CronJob[];
  botLabel: string;
  botColor: string;
  busyJobId?: number | null;
  onInspect?: (job: CronJob) => void;
  onEdit?: (job: CronJob) => void;
  onRun?: (job: CronJob) => void;
  onLifecycleAction?: (job: CronJob, action: ScheduleLifecycleAction) => void;
}

function getLifecycleAction(job: CronJob): {
  action: ScheduleLifecycleAction | null;
  label: string;
  disabled: boolean;
} {
  switch (job.status) {
    case "active":
      return { action: "pause", label: "Pause", disabled: false };
    case "paused":
      return { action: "resume", label: "Resume", disabled: false };
    case "validated":
      return { action: "resume", label: "Activate", disabled: false };
    case "failed_open":
      return { action: "resume", label: "Resume", disabled: false };
    case "validation_pending":
      return { action: null, label: "Validation pending", disabled: true };
    default:
      return { action: job.enabled === 1 ? "pause" : "resume", label: job.enabled === 1 ? "Pause" : "Activate", disabled: false };
  }
}

export function CronTable({
  jobs,
  botLabel,
  botColor,
  busyJobId = null,
  onInspect,
  onEdit,
  onRun,
  onLifecycleAction,
}: CronTableProps) {
  const { t } = useAppI18n();
  if (jobs.length === 0) {
    return (
      <div className="app-section px-6 py-8 text-center">
        <Clock className="mx-auto h-10 w-10 text-[var(--text-tertiary)]" />
        <p className="mt-4 text-sm font-medium text-[var(--text-primary)]">
          <span style={{ color: botColor }}>{t("schedules.table.noRoutine", { bot: botLabel })}</span>
        </p>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          {t("schedules.table.noRoutineDescription")}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:hidden">
        {jobs.map((job) => (
          <article key={job.id} className="app-card-row">
            <div className="flex items-start justify-between gap-3">
              <span className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1 font-mono text-[11px] text-[var(--text-primary)]">
                {job.cron_expression}
              </span>
              <StatusBadge status={job.status} />
            </div>
            <p
              className="mt-3 text-sm font-medium leading-6 text-[var(--text-primary)]"
              title={job.command}
            >
              {truncateText(job.command, 72)}
            </p>
            <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
              {job.description || t("schedules.table.noSummary")}
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2.5">
              <MobileScheduleStat
                icon={TerminalSquare}
                label={t("schedules.table.routine")}
                value={truncateText(job.command, 30)}
              />
              <MobileScheduleStat
                icon={FolderTree}
                label={t("schedules.table.scope")}
                value={job.work_dir ?? t("schedules.table.noDirectory")}
                mono
              />
            </div>
            <JobActions
              job={job}
              busy={busyJobId === job.id}
              onInspect={onInspect}
              onEdit={onEdit}
              onRun={onRun}
              onLifecycleAction={onLifecycleAction}
            />
          </article>
        ))}
      </div>

      <div className="hidden md:block">
        <div className="table-shell overflow-x-auto">
          <table className="glass-table">
            <thead>
              <tr>
                <th>{t("schedules.table.schedule")}</th>
                <th>{t("schedules.table.routine")}</th>
                <th>{t("common.summary")}</th>
                <th>{t("schedules.table.nextRun", { defaultValue: "Next run" })}</th>
                <th className="text-right">{t("common.status")}</th>
                <th>{t("schedules.table.scope")}</th>
                <th className="text-right">{t("common.actions", { defaultValue: "Actions" })}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>
                    <span className="inline-flex items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--field-bg)] px-2.5 py-1 font-mono text-[11px] text-[var(--text-primary)]">
                      {job.cron_expression}
                    </span>
                  </td>
                  <td>
                    <div className="min-w-[16rem]">
                      <p
                        className="text-[13px] font-medium leading-6 text-[var(--text-primary)]"
                        title={job.command}
                      >
                        {truncateText(job.command, 58)}
                      </p>
                    </div>
                  </td>
                  <td>
                    <span className="text-[13px] leading-6 text-[var(--text-secondary)]">
                      {job.description || t("schedules.table.noSummary")}
                    </span>
                  </td>
                  <td>
                    <span className="text-[13px] leading-6 text-[var(--text-secondary)]">
                      {job.next_run_at || "pending validation"}
                    </span>
                  </td>
                  <td className="text-right">
                    <StatusBadge status={job.status} />
                  </td>
                  <td>
                    <span className="font-mono text-xs text-[var(--text-tertiary)]">
                      {job.work_dir ?? t("schedules.table.noDirectory")}
                    </span>
                  </td>
                  <td className="text-right">
                    <JobActions
                      job={job}
                      busy={busyJobId === job.id}
                      onInspect={onInspect}
                      onEdit={onEdit}
                      onRun={onRun}
                      onLifecycleAction={onLifecycleAction}
                      compact
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function JobActions({
  job,
  busy,
  onInspect,
  onEdit,
  onRun,
  onLifecycleAction,
  compact = false,
}: {
  job: CronJob;
  busy: boolean;
  onInspect?: (job: CronJob) => void;
  onEdit?: (job: CronJob) => void;
  onRun?: (job: CronJob) => void;
  onLifecycleAction?: (job: CronJob, action: ScheduleLifecycleAction) => void;
  compact?: boolean;
}) {
  const baseClass =
    "inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] px-2.5 py-1.5 text-[11px] font-medium text-[var(--text-secondary)] transition hover:border-[var(--border-strong)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50";
  const lifecycle = getLifecycleAction(job);

  return (
    <div className={`mt-4 flex ${compact ? "justify-end" : "flex-wrap"} gap-2`}>
      <button type="button" className={baseClass} onClick={() => onInspect?.(job)} disabled={busy}>
        <Clock className="h-3.5 w-3.5" />
        {compact ? "Inspect" : "Detalhes"}
      </button>
      <button type="button" className={baseClass} onClick={() => onEdit?.(job)} disabled={busy}>
        <Pencil className="h-3.5 w-3.5" />
        Edit
      </button>
      <button type="button" className={baseClass} onClick={() => onRun?.(job)} disabled={busy}>
        <Play className="h-3.5 w-3.5" />
        Run
      </button>
      <button
        type="button"
        className={baseClass}
        onClick={() => lifecycle.action && onLifecycleAction?.(job, lifecycle.action)}
        disabled={busy || lifecycle.disabled}
      >
        {lifecycle.label}
      </button>
    </div>
  );
}

function StatusBadge({ status }: { status?: string | null }) {
  const { t } = useAppI18n();
  let tone: Parameters<typeof getSemanticStyle>[0] = "neutral";
  let label = status || "unknown";

  switch (status ?? "") {
    case "active":
      tone = "success";
      label = t("common.active");
      break;
    case "paused":
      tone = "neutral";
      label = t("common.paused");
      break;
    case "validation_pending":
      tone = "warning";
      label = "Validating";
      break;
    case "validated":
      tone = "info";
      label = "Validated";
      break;
    case "failed_open":
      tone = "danger";
      label = "Failed open";
      break;
  }

  return (
    <span
      className="inline-flex min-h-[28px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10.5px] font-semibold"
      style={getSemanticStyle(tone)}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={getSemanticDotStyle(tone)} />
      {label}
    </span>
  );
}

function MobileScheduleStat({
  icon: Icon,
  label,
  value,
  mono = false,
}: {
  icon: typeof Clock;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.012)] px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-quaternary)]">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </p>
      <p
        className={
          mono
            ? "mt-1 break-all font-mono text-[12px] text-[var(--text-secondary)]"
            : "mt-1 text-[12px] text-[var(--text-secondary)]"
        }
      >
        {value}
      </p>
    </div>
  );
}
