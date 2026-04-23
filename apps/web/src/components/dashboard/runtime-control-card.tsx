"use client";

import { memo } from "react";
import Link from "next/link";
import { ArrowRight, ShieldAlert } from "lucide-react";
import { useRuntimeOverview } from "@/hooks/use-runtime-overview";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getAgentLabel } from "@/lib/agent-constants";
import {
  buildRuntimeRoomRows,
  getRuntimeRowSummary,
} from "@/lib/runtime-overview-model";
import { getSemanticStyle } from "@/lib/theme-semantic";
import { getRuntimeLabel, getRuntimeTone } from "@/lib/runtime-ui";
import { formatRelativeTime, truncateText } from "@/lib/utils";

interface RuntimeControlCardProps {
  selectedBotIds?: string[];
}

export const RuntimeControlCard = memo(function RuntimeControlCard({ selectedBotIds }: RuntimeControlCardProps) {
  const { t } = useAppI18n();
  const { overviews, loading, connected } = useRuntimeOverview(selectedBotIds);
  const selected = Object.values(overviews);
  const rows = buildRuntimeRoomRows(selected)
    .filter((row) =>
      ["active", "running", "queued", "retrying", "cleaning", "retained"].includes(row.status)
    )
    .slice(0, 5);

  const totals = selected.reduce(
    (acc, overview) => {
      acc.active += overview.snapshot?.active_environments ?? 0;
      acc.retained += overview.snapshot?.retained_environments ?? 0;
      acc.incidents += overview.incidents.length;
      return acc;
    },
    { active: 0, retained: 0, incidents: 0 }
  );

  return (
    <section className="glass-card animate-in stagger-4 p-5 sm:p-6 lg:p-7">
      <div className="mb-5 flex flex-col gap-3 border-b border-[var(--border-subtle)] pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="eyebrow">{t("runtime.controlCard.eyebrow")}</p>
          <h3 className="mt-1.5 text-[1.22rem] font-semibold tracking-[-0.05em] text-[var(--text-primary)] sm:text-[1.35rem]">
            {t("runtime.controlCard.title")}
          </h3>
          <p className="mt-1 text-sm text-[var(--text-tertiary)]">
            {t("runtime.controlCard.description")}
          </p>
        </div>
        <Link href="/runtime" className="button-pill is-active">
          {t("runtime.controlCard.openRuntime")}
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <RuntimeControlStat label={t("runtime.controlCard.active")} value={String(totals.active)} />
        <RuntimeControlStat label={t("runtime.controlCard.retained")} value={String(totals.retained)} />
        <RuntimeControlStat label={t("runtime.controlCard.incidents")} value={String(totals.incidents)} />
      </div>

      <div className="mt-5 space-y-3">
        {loading && rows.length === 0 ? (
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-5 text-sm text-[var(--text-tertiary)]">
            {t("runtime.controlCard.loading")}
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] p-5 text-sm text-[var(--text-tertiary)]">
            {t("runtime.controlCard.empty")}
          </div>
        ) : (
          rows.map((row) => (
            <Link
              key={`${row.agentId}-${row.taskId}`}
              href={`/runtime/${row.agentId}/tasks/${row.taskId}`}
              className="group flex items-center justify-between gap-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3 transition-colors hover:bg-[var(--surface-hover)]"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="chip">{getAgentLabel(row.agentId)}</span>
                  <span
                    className="inline-flex rounded-lg border px-2.5 py-1 text-[10px] font-semibold tracking-[0.03em]"
                    style={getSemanticStyle(getRuntimeTone(row.phase))}
                  >
                    {getRuntimeLabel(row.phase)}
                  </span>
                  <span className="chip font-mono">#{row.taskId}</span>
                  {connected[row.agentId] ? <span className="chip">{t("runtime.controlCard.live")}</span> : null}
                </div>
                <p className="mt-2 text-sm text-[var(--text-primary)]">
                  {truncateText(getRuntimeRowSummary(row), 104)}
                </p>
                <p className="mt-1 truncate font-mono text-[11px] text-[var(--text-quaternary)]">
                  {truncateText(
                    row.environment?.workspace_path ||
                      row.environment?.branch_name ||
                      row.queue?.queue_name ||
                      row.source,
                    88
                  )}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-[var(--text-tertiary)]">
                  {formatRelativeTime(row.updatedAt)}
                </p>
                <ArrowRight className="ml-auto mt-2 h-4 w-4 text-[var(--text-quaternary)] transition-colors group-hover:text-[var(--text-secondary)]" />
              </div>
            </Link>
          ))
        )}
      </div>

      {selected.some((overview) => overview.incidents.length > 0) ? (
        <div className="mt-5 rounded-lg border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)]/55 p-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-4 w-4 text-[var(--tone-warning-text)]" />
            <p className="text-sm leading-6 text-[var(--tone-warning-muted)]">
              {t("runtime.controlCard.backlogNotice")}
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
});

function RuntimeControlStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-tint)] px-4 py-3">
      <p className="text-[10px] uppercase tracking-[0.14em] text-[var(--text-quaternary)]">
        {label}
      </p>
      <p className="mt-2 text-[1.45rem] font-semibold tracking-[-0.06em] text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
