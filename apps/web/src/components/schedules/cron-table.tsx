"use client";

import { Clock, Pencil, Play } from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { CronJob } from "@/lib/types";
import { cn, truncateText } from "@/lib/utils";

type ScheduleLifecycleAction = "pause" | "resume" | "validate";

interface CronTableProps {
  jobs: CronJob[];
  agentLabel: string;
  agentColor: string;
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
      return {
        action: job.enabled === 1 ? "pause" : "resume",
        label: job.enabled === 1 ? "Pause" : "Activate",
        disabled: false,
      };
  }
}

export function CronTable({
  jobs,
  agentLabel,
  agentColor,
  busyJobId = null,
  onInspect,
  onEdit,
  onRun,
  onLifecycleAction,
}: CronTableProps) {
  const { t } = useAppI18n();
  if (jobs.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center">
        <Clock
          className="icon-lg text-[var(--text-quaternary)]"
          strokeWidth={1.5}
          aria-hidden
        />
        <p className="m-0 text-[var(--font-size-sm)] font-medium text-[var(--text-primary)]">
          <span style={{ color: agentColor }}>
            {t("schedules.table.noRoutine", { agent: agentLabel })}
          </span>
        </p>
        <p className="m-0 text-[0.75rem] text-[var(--text-tertiary)]">
          {t("schedules.table.noRoutineDescription")}
        </p>
      </div>
    );
  }

  const thClass =
    "py-2.5 pr-4 text-left font-mono text-[0.6875rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]";
  const thRightClass = `${thClass} text-right`;

  return (
    <div>
      <div className="flex flex-col md:hidden">
        {jobs.map((job) => (
          <article
            key={job.id}
            className="flex flex-col gap-2 border-b border-[color:var(--divider-hair)] py-3 last:border-b-0"
          >
            <div className="flex items-start justify-between gap-3">
              <span className="font-mono text-[0.75rem] text-[var(--text-primary)]">
                {job.cron_expression}
              </span>
              <StatusBadge status={job.status} />
            </div>
            <p
              className="m-0 text-[0.8125rem] leading-[1.5] text-[var(--text-primary)]"
              title={job.command}
            >
              {truncateText(job.command, 72)}
            </p>
            {job.description ? (
              <p className="m-0 text-[0.75rem] leading-[1.5] text-[var(--text-tertiary)]">
                {job.description}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
              {job.work_dir ? (
                <span>
                  dir: <span className="text-[var(--text-secondary)]">{job.work_dir}</span>
                </span>
              ) : null}
              <span>
                next:{" "}
                <span className="text-[var(--text-secondary)]">
                  {job.next_run_at || "pending"}
                </span>
              </span>
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
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[color:var(--divider-hair)]">
                <th className={thClass}>{t("schedules.table.schedule")}</th>
                <th className={thClass}>{t("schedules.table.routine")}</th>
                <th className={thClass}>{t("common.summary")}</th>
                <th className={thClass}>
                  {t("schedules.table.nextRun", { defaultValue: "Next run" })}
                </th>
                <th className={thRightClass}>{t("common.status")}</th>
                <th className={thClass}>{t("schedules.table.scope")}</th>
                <th className={thRightClass}>
                  {t("common.actions", { defaultValue: "Actions" })}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--divider-hair)]">
              {jobs.map((job) => (
                <tr key={job.id} className="transition-colors duration-[120ms] hover:bg-[var(--hover-tint)]">
                  <td className="py-3 pr-4">
                    <span className="font-mono text-[0.75rem] text-[var(--text-primary)]">
                      {job.cron_expression}
                    </span>
                  </td>
                  <td className="py-3 pr-4">
                    <p
                      className="m-0 line-clamp-1 text-[0.8125rem] text-[var(--text-primary)]"
                      title={job.command}
                    >
                      {truncateText(job.command, 58)}
                    </p>
                  </td>
                  <td className="py-3 pr-4">
                    <span className="text-[0.8125rem] text-[var(--text-secondary)]">
                      {job.description || t("schedules.table.noSummary")}
                    </span>
                  </td>
                  <td className="py-3 pr-4">
                    <span className="font-mono text-[0.75rem] text-[var(--text-secondary)]">
                      {job.next_run_at || "pending"}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-right">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="py-3 pr-4">
                    <span className="font-mono text-[0.75rem] text-[var(--text-tertiary)]">
                      {job.work_dir ?? t("schedules.table.noDirectory")}
                    </span>
                  </td>
                  <td className="py-3 text-right">
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
  const baseClass = cn(
    "inline-flex h-8 items-center gap-1 rounded-[var(--radius-pill)] border border-[color:var(--border-subtle)] bg-transparent px-2.5 text-[0.75rem] font-medium text-[var(--text-secondary)]",
    "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
    "hover:border-[color:var(--border-strong)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
    "disabled:cursor-not-allowed disabled:opacity-50",
  );
  const lifecycle = getLifecycleAction(job);

  return (
    <div className={cn("flex gap-1.5", compact ? "justify-end" : "flex-wrap")}>
      <button type="button" className={baseClass} onClick={() => onInspect?.(job)} disabled={busy}>
        <Clock className="icon-xs" strokeWidth={1.75} aria-hidden />
        {compact ? "Inspect" : "Detalhes"}
      </button>
      <button type="button" className={baseClass} onClick={() => onEdit?.(job)} disabled={busy}>
        <Pencil className="icon-xs" strokeWidth={1.75} aria-hidden />
        Edit
      </button>
      <button type="button" className={baseClass} onClick={() => onRun?.(job)} disabled={busy}>
        <Play className="icon-xs" strokeWidth={1.75} aria-hidden />
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
  let tone: StatusDotTone = "neutral";
  let label = status || "unknown";
  let pulse = false;

  switch (status ?? "") {
    case "active":
      tone = "success";
      label = t("common.active");
      pulse = true;
      break;
    case "paused":
      tone = "neutral";
      label = t("common.paused");
      break;
    case "validation_pending":
      tone = "warning";
      label = "Validating";
      pulse = true;
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
    <span className="inline-flex items-center gap-1.5 text-[0.75rem] text-[var(--text-secondary)]">
      <StatusDot tone={tone} pulse={pulse} />
      {label}
    </span>
  );
}
