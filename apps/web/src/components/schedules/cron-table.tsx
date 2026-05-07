"use client";

import type { ReactNode } from "react";
import {
  Check,
  Clock,
  History,
  Loader2,
  Pause,
  Pencil,
  Play,
  RotateCcw,
  X,
  type LucideIcon,
} from "lucide-react";
import { AgentSigil } from "@/components/control-plane/shared/agent-sigil";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { AgentDisplay } from "@/lib/agent-constants";
import type { CronJob } from "@/lib/types";
import { cn, truncateText } from "@/lib/utils";

type ScheduleLifecycleAction = "pause" | "resume" | "validate";
export type ScheduleTableActionKey = "inspect" | "edit" | "executions" | "run" | "lifecycle";
export type ScheduleTableActionState = "idle" | "pending" | "success" | "error";
export type ScheduleTableActionStates = Partial<
  Record<number, Partial<Record<ScheduleTableActionKey, ScheduleTableActionState>>>
>;

export interface CronTableRow {
  job: CronJob;
  agent: AgentDisplay;
}

interface CronTableProps {
  rows: CronTableRow[];
  busyJobId?: number | null;
  actionStates?: ScheduleTableActionStates;
  onInspect?: (job: CronJob) => void;
  onEdit?: (job: CronJob) => void;
  onExecutions?: (job: CronJob) => void;
  onRun?: (job: CronJob) => void;
  onLifecycleAction?: (job: CronJob, action: ScheduleLifecycleAction) => void;
}

function getLifecycleAction(job: CronJob): {
  action: ScheduleLifecycleAction | null;
  label: string;
  disabled: boolean;
  icon: LucideIcon;
} {
  switch (job.status) {
    case "active":
      return { action: "pause", label: "Pause", disabled: false, icon: Pause };
    case "paused":
      return { action: "resume", label: "Resume", disabled: false, icon: RotateCcw };
    case "validated":
      return { action: "resume", label: "Activate", disabled: false, icon: Play };
    case "failed_open":
      return { action: "resume", label: "Resume", disabled: false, icon: RotateCcw };
    case "validation_pending":
      return { action: null, label: "Validation pending", disabled: true, icon: Clock };
    default:
      return {
        action: job.enabled === 1 ? "pause" : "resume",
        label: job.enabled === 1 ? "Pause" : "Activate",
        disabled: false,
        icon: job.enabled === 1 ? Pause : Play,
      };
  }
}

function getPayloadString(job: CronJob, key: string): string {
  const value = job.payload?.[key];
  return typeof value === "string" ? value.trim() : "";
}

function getRoutineName(job: CronJob): string {
  return job.summary?.trim() || getPayloadString(job, "name") || truncateText(job.command, 56);
}

function getRoutineSummary(job: CronJob): string {
  return (
    job.description?.trim() ||
    getPayloadString(job, "query") ||
    getPayloadString(job, "text") ||
    getPayloadString(job, "command") ||
    job.command
  );
}

function formatScheduleTimestamp(value: string | null | undefined): string {
  if (!value) return "pending";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function CronTable({
  rows,
  busyJobId = null,
  actionStates,
  onInspect,
  onEdit,
  onExecutions,
  onRun,
  onLifecycleAction,
}: CronTableProps) {
  const { t } = useAppI18n();

  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center">
        <Clock
          className="icon-lg text-[var(--text-quaternary)]"
          strokeWidth={1.5}
          aria-hidden
        />
        <p className="m-0 text-[var(--font-size-sm)] font-medium text-[var(--text-primary)]">
          {t("schedules.table.noRoutine", {
            bot: t("common.agents", { defaultValue: "agents" }),
          })}
        </p>
        <p className="m-0 text-[0.75rem] text-[var(--text-tertiary)]">
          {t("schedules.table.noRoutineDescription")}
        </p>
      </div>
    );
  }

  const cols =
    "md:grid-cols-[minmax(160px,180px)_minmax(260px,1fr)_minmax(128px,150px)_96px_minmax(150px,190px)_176px]";
  const headerClass =
    "px-1 font-mono text-[0.6875rem] font-medium uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]";

  return (
    <TooltipProvider delayDuration={250}>
      <div className="overflow-x-auto overflow-y-hidden rounded-[var(--radius-shell)] border border-[color:var(--border-subtle)] bg-[var(--panel)] overscroll-x-contain">
        <div className="hidden min-w-[1060px] md:block" role="table">
          <div
            className={cn(
              "grid items-center gap-3 border-b border-[color:var(--divider-hair)] px-4 py-2.5",
              cols,
            )}
            role="row"
          >
            <span className={headerClass} role="columnheader">
              {t("common.agent", { defaultValue: "Agent" })}
            </span>
            <span className={headerClass} role="columnheader">
              {t("schedules.table.routine")}
            </span>
            <span className={headerClass} role="columnheader">
              {t("schedules.table.schedule")}
            </span>
            <span className={cn(headerClass, "text-right")} role="columnheader">
              {t("common.status")}
            </span>
            <span className={headerClass} role="columnheader">
              {t("schedules.table.scope")}
            </span>
            <span
              className={cn(
                headerClass,
                "sticky-table-last sticky-table-last--header -mr-4 py-1.5 pl-4 pr-4 text-right",
              )}
              role="columnheader"
            >
              {t("common.actions", { defaultValue: "Actions" })}
            </span>
          </div>

          <div className="flex flex-col" role="rowgroup">
            {rows.map((row) => (
              <ScheduleDesktopRow
                key={`${row.agent.id}-${row.job.id}`}
                row={row}
                cols={cols}
                busy={busyJobId === row.job.id}
                actionStates={actionStates?.[row.job.id]}
                onInspect={onInspect}
                onEdit={onEdit}
                onExecutions={onExecutions}
                onRun={onRun}
                onLifecycleAction={onLifecycleAction}
              />
            ))}
          </div>
        </div>

        <div className="flex flex-col md:hidden">
          {rows.map((row) => (
            <ScheduleMobileRow
              key={`${row.agent.id}-${row.job.id}`}
              row={row}
              busy={busyJobId === row.job.id}
              actionStates={actionStates?.[row.job.id]}
              onInspect={onInspect}
              onEdit={onEdit}
              onExecutions={onExecutions}
              onRun={onRun}
              onLifecycleAction={onLifecycleAction}
            />
          ))}
        </div>
      </div>
    </TooltipProvider>
  );
}

function ScheduleDesktopRow({
  row,
  cols,
  busy,
  actionStates,
  onInspect,
  onEdit,
  onExecutions,
  onRun,
  onLifecycleAction,
}: {
  row: CronTableRow;
  cols: string;
  busy: boolean;
  actionStates?: Partial<Record<ScheduleTableActionKey, ScheduleTableActionState>>;
  onInspect?: (job: CronJob) => void;
  onEdit?: (job: CronJob) => void;
  onExecutions?: (job: CronJob) => void;
  onRun?: (job: CronJob) => void;
  onLifecycleAction?: (job: CronJob, action: ScheduleLifecycleAction) => void;
}) {
  const { t } = useAppI18n();
  const { agent, job } = row;
  const routineName = getRoutineName(job);
  const routineSummary = getRoutineSummary(job);

  return (
    <div
      className={cn(
        "group grid items-center gap-3 border-b border-[color:var(--divider-hair)] px-4 py-3 last:border-b-0",
        "sticky-table-row",
        "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[var(--hover-tint)]",
        cols,
      )}
      role="row"
    >
      <div className="flex min-w-0 items-center gap-2.5" role="cell">
        <AgentSigil
          agentId={agent.id}
          label={agent.label}
          color={agent.color}
          status={job.status}
          size="sm"
        />
        <span className="flex min-w-0 flex-col leading-tight">
          <span className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
            {agent.label}
          </span>
          <span className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
            {agent.id}
          </span>
        </span>
      </div>

      <div className="min-w-0" role="cell">
        <p
          className="m-0 line-clamp-1 text-[0.8125rem] font-medium text-[var(--text-primary)]"
          title={routineName}
        >
          {routineName}
        </p>
        <p
          className="m-0 mt-1 line-clamp-1 text-[0.75rem] leading-[1.45] text-[var(--text-tertiary)]"
          title={routineSummary}
        >
          {routineSummary || t("schedules.table.noSummary")}
        </p>
      </div>

      <div className="min-w-0" role="cell">
        <span className="block truncate font-mono text-[0.75rem] tabular-nums text-[var(--text-secondary)]">
          {job.schedule_expr || job.cron_expression}
        </span>
        <span className="mt-1 block truncate font-mono text-[0.6875rem] uppercase text-[var(--text-quaternary)]">
          {job.timezone || "UTC"}
        </span>
      </div>

      <div className="flex justify-end" role="cell">
        <StatusBadge status={job.status} />
      </div>

      <div className="min-w-0" role="cell">
        <span
          className="block truncate font-mono text-[0.75rem] text-[var(--text-tertiary)]"
          title={job.work_dir ?? undefined}
        >
          {job.work_dir ?? t("schedules.table.noDirectory")}
        </span>
      </div>

      <div
        className="sticky-table-last -mr-4 flex justify-end py-1 pl-4 pr-4"
        role="cell"
      >
        <JobActions
          job={job}
          busy={busy}
          onInspect={onInspect}
          onEdit={onEdit}
          onRun={onRun}
          onLifecycleAction={onLifecycleAction}
          actionStates={actionStates}
          compact
          onExecutions={onExecutions}
        />
      </div>
    </div>
  );
}

function ScheduleMobileRow({
  row,
  busy,
  actionStates,
  onInspect,
  onEdit,
  onExecutions,
  onRun,
  onLifecycleAction,
}: {
  row: CronTableRow;
  busy: boolean;
  actionStates?: Partial<Record<ScheduleTableActionKey, ScheduleTableActionState>>;
  onInspect?: (job: CronJob) => void;
  onEdit?: (job: CronJob) => void;
  onExecutions?: (job: CronJob) => void;
  onRun?: (job: CronJob) => void;
  onLifecycleAction?: (job: CronJob, action: ScheduleLifecycleAction) => void;
}) {
  const { t } = useAppI18n();
  const { agent, job } = row;
  const routineName = getRoutineName(job);
  const routineSummary = getRoutineSummary(job);

  return (
    <article className="flex flex-col gap-3 border-b border-[color:var(--divider-hair)] px-4 py-3 last:border-b-0">
      <div className="flex items-start gap-3">
        <AgentSigil
          agentId={agent.id}
          label={agent.label}
          color={agent.color}
          status={job.status}
          size="sm"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <span className="truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
              {agent.label}
            </span>
            <StatusBadge status={job.status} />
          </div>
          <p className="m-0 mt-1 line-clamp-1 text-[0.8125rem] text-[var(--text-primary)]">
            {routineName}
          </p>
          <p className="m-0 mt-1 line-clamp-2 text-[0.75rem] leading-[1.5] text-[var(--text-tertiary)]">
            {routineSummary || t("schedules.table.noSummary")}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
        <span className="min-w-0">
          {t("schedules.table.schedule")}:{" "}
          <span className="text-[var(--text-secondary)]">
            {job.schedule_expr || job.cron_expression}
          </span>
        </span>
        <span className="min-w-0">
          {t("schedules.table.nextRun", { defaultValue: "Next run" })}:{" "}
          <span className="text-[var(--text-secondary)]">
            {formatScheduleTimestamp(job.next_run_at)}
          </span>
        </span>
        <span className="col-span-2 min-w-0 truncate" title={job.work_dir ?? undefined}>
          {t("schedules.table.scope")}:{" "}
          <span className="text-[var(--text-secondary)]">
            {job.work_dir ?? t("schedules.table.noDirectory")}
          </span>
        </span>
      </div>

      <JobActions
        job={job}
        busy={busy}
        onInspect={onInspect}
        onEdit={onEdit}
        onExecutions={onExecutions}
        onRun={onRun}
        onLifecycleAction={onLifecycleAction}
        actionStates={actionStates}
      />
    </article>
  );
}

function JobActions({
  job,
  busy,
  onInspect,
  onEdit,
  onExecutions,
  onRun,
  onLifecycleAction,
  actionStates,
  compact = false,
}: {
  job: CronJob;
  busy: boolean;
  onInspect?: (job: CronJob) => void;
  onEdit?: (job: CronJob) => void;
  onExecutions?: (job: CronJob) => void;
  onRun?: (job: CronJob) => void;
  onLifecycleAction?: (job: CronJob, action: ScheduleLifecycleAction) => void;
  actionStates?: Partial<Record<ScheduleTableActionKey, ScheduleTableActionState>>;
  compact?: boolean;
}) {
  const { t } = useAppI18n();
  const lifecycle = getLifecycleAction(job);
  const LifecycleIcon = lifecycle.icon;
  const inspectState = actionStates?.inspect ?? "idle";
  const editState = actionStates?.edit ?? "idle";
  const executionsState = actionStates?.executions ?? "idle";
  const runState = actionStates?.run ?? "idle";
  const lifecycleState = actionStates?.lifecycle ?? "idle";

  return (
    <div className={cn("flex gap-1", compact ? "justify-end" : "flex-wrap")}>
      <ActionButton
        label="Inspect"
        onClick={() => onInspect?.(job)}
        disabled={busy}
        state={inspectState}
      >
        <Clock className="icon-xs" strokeWidth={1.75} aria-hidden />
      </ActionButton>
      <ActionButton
        label="Edit"
        onClick={() => onEdit?.(job)}
        disabled={busy}
        state={editState}
      >
        <Pencil className="icon-xs" strokeWidth={1.75} aria-hidden />
      </ActionButton>
      <ActionButton
        label={t("schedules.table.executionsAction", { defaultValue: "Executions" })}
        onClick={() => onExecutions?.(job)}
        disabled={busy}
        state={executionsState}
      >
        <History className="icon-xs" strokeWidth={1.75} aria-hidden />
      </ActionButton>
      <ActionButton
        label="Run now"
        onClick={() => onRun?.(job)}
        disabled={busy}
        state={runState}
      >
        <Play className="icon-xs" strokeWidth={1.75} aria-hidden />
      </ActionButton>
      <ActionButton
        label={lifecycle.label}
        onClick={() => lifecycle.action && onLifecycleAction?.(job, lifecycle.action)}
        disabled={busy || lifecycle.disabled}
        state={lifecycleState}
      >
        <LifecycleIcon className="icon-xs" strokeWidth={1.75} aria-hidden />
      </ActionButton>
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  disabled,
  state = "idle",
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  state?: ScheduleTableActionState;
  children: ReactNode;
}) {
  const isPending = state === "pending";
  const isResolved = state === "success" || state === "error";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label}
          aria-busy={isPending || undefined}
          title={label}
          data-action-state={state}
          className={cn(
            "inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-chip)] border border-transparent text-[var(--text-tertiary)]",
            "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
            "hover:border-[color:var(--border-subtle)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
            "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)]",
            "disabled:cursor-not-allowed disabled:opacity-50",
            state === "pending" && "border-[color:var(--border-subtle)] bg-[var(--panel-soft)] text-[var(--text-secondary)] opacity-100",
            state === "success" && "border-[color:var(--tone-success-border)] bg-[var(--tone-success-bg)] text-[var(--tone-success-dot)] opacity-100",
            state === "error" && "border-[color:var(--tone-danger-border)] bg-[var(--tone-danger-bg)] text-[var(--tone-danger-dot)] opacity-100",
          )}
          onClick={onClick}
          disabled={disabled || isPending}
        >
          {isPending ? (
            <Loader2 className="icon-xs animate-spin" strokeWidth={1.75} aria-hidden />
          ) : state === "success" ? (
            <Check className="icon-xs" strokeWidth={1.75} aria-hidden />
          ) : state === "error" ? (
            <X className="icon-xs" strokeWidth={1.75} aria-hidden />
          ) : (
            children
          )}
          {isResolved ? <span className="sr-only">{state}</span> : null}
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
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
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[0.75rem] text-[var(--text-secondary)]">
      <StatusDot tone={tone} pulse={pulse} />
      {label}
    </span>
  );
}
