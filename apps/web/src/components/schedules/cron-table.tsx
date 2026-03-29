"use client";

import { Clock, FolderTree, TerminalSquare } from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { CronJob } from "@/lib/types";
import { getSemanticDotStyle, getSemanticStyle } from "@/lib/theme-semantic";
import { truncateText } from "@/lib/utils";

interface CronTableProps {
  jobs: CronJob[];
  botLabel: string;
  botColor: string;
}

export function CronTable({ jobs, botLabel, botColor }: CronTableProps) {
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
              <StatusBadge enabled={job.enabled === 1} />
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
                <th className="text-right">{t("common.status")}</th>
                <th>{t("schedules.table.scope")}</th>
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
                  <td className="text-right">
                    <StatusBadge enabled={job.enabled === 1} />
                  </td>
                  <td>
                    <span className="font-mono text-xs text-[var(--text-tertiary)]">
                      {job.work_dir ?? t("schedules.table.noDirectory")}
                    </span>
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

function StatusBadge({ enabled }: { enabled: boolean }) {
  const { t } = useAppI18n();
  return enabled ? (
    <span className="inline-flex min-h-[28px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10.5px] font-semibold" style={getSemanticStyle("success")}>
      <span className="h-1.5 w-1.5 rounded-full" style={getSemanticDotStyle("success")} />
      {t("common.active")}
    </span>
  ) : (
    <span className="inline-flex min-h-[28px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10.5px] font-semibold" style={getSemanticStyle("neutral")}>
      <span className="h-1.5 w-1.5 rounded-full" style={getSemanticDotStyle("neutral")} />
      {t("common.paused")}
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
