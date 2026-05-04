"use client";

import { memo } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useRuntimeOverview } from "@/hooks/use-runtime-overview";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { getAgentLabel } from "@/lib/agent-constants";
import {
  buildRuntimeRoomRows,
  getRuntimeRowSummary,
} from "@/lib/runtime-overview-model";
import type { SemanticTone } from "@/lib/theme-semantic";
import { getRuntimeLabel, getRuntimeTone } from "@/lib/runtime-ui";
import { InlineAlert } from "@/components/ui/inline-alert";
import { PageMetricStrip, PageMetricStripItem } from "@/components/ui/page-primitives";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { formatRelativeTime, truncateText } from "@/lib/utils";

interface RuntimeControlCardProps {
  selectedBotIds?: string[];
}

function toneToStatusDot(tone: SemanticTone): StatusDotTone {
  if (tone === "success" || tone === "info" || tone === "warning" || tone === "danger" || tone === "retry" || tone === "neutral") {
    return tone;
  }
  return "neutral";
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
    <section className="animate-in stagger-4">
      <div className="mb-4 flex flex-col gap-3 border-b border-[color:var(--divider-hair)] pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="eyebrow">{t("runtime.controlCard.eyebrow")}</p>
          <h3 className="m-0 mt-1.5 text-[1.0625rem] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
            {t("runtime.controlCard.title")}
          </h3>
          <p className="m-0 mt-1 max-w-2xl text-[0.8125rem] leading-5 text-[var(--text-tertiary)]">
            {t("runtime.controlCard.description")}
          </p>
        </div>
        <Link
          href="/runtime"
          className="inline-flex h-8 shrink-0 items-center justify-center rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 text-[0.8125rem] font-medium text-[var(--text-primary)] transition-[background-color,border-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--border-strong)] hover:bg-[var(--hover-tint)]"
        >
          {t("runtime.controlCard.openRuntime")}
        </Link>
      </div>

      <PageMetricStrip>
        <PageMetricStripItem
          label={t("runtime.controlCard.active")}
          value={String(totals.active)}
          tone={totals.active > 0 ? "accent" : "neutral"}
        />
        <PageMetricStripItem
          label={t("runtime.controlCard.retained")}
          value={String(totals.retained)}
          tone={totals.retained > 0 ? "success" : "neutral"}
        />
        <PageMetricStripItem
          label={t("runtime.controlCard.incidents")}
          value={String(totals.incidents)}
          tone={totals.incidents > 0 ? "warning" : "neutral"}
        />
      </PageMetricStrip>

      <div className="mt-4 flex flex-col">
        {loading && rows.length === 0 ? (
          <div className="py-8 text-center text-[0.8125rem] text-[var(--text-tertiary)]">
            {t("runtime.controlCard.loading")}
          </div>
        ) : rows.length === 0 ? (
          <div className="py-8 text-center text-[0.8125rem] text-[var(--text-tertiary)]">
            {t("runtime.controlCard.empty")}
          </div>
        ) : (
          rows.map((row, index) => {
            const phaseTone = toneToStatusDot(getRuntimeTone(row.phase));
            return (
              <Link
                key={`${row.agentId}-${row.taskId}`}
                href={`/runtime/${row.agentId}/tasks/${row.taskId}`}
                className={[
                  "group grid grid-cols-[1fr_auto] items-center gap-3 rounded-[var(--radius-panel-sm)] px-3 py-3 transition-colors",
                  "hover:bg-[var(--hover-tint)] focus-visible:bg-[var(--hover-tint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
                  index > 0 ? "border-t border-[color:var(--divider-hair)]" : "",
                ].join(" ")}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
                      {getAgentLabel(row.agentId)} #{row.taskId}
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-[0.6875rem] text-[var(--text-secondary)]">
                      <StatusDot tone={phaseTone} pulse={phaseTone === "info" || phaseTone === "warning"} />
                      {getRuntimeLabel(row.phase)}
                    </span>
                    {connected[row.agentId] ? (
                      <span className="inline-flex items-center gap-1.5 text-[0.6875rem] text-[var(--text-tertiary)]">
                        <StatusDot tone="success" pulse />
                        {t("runtime.controlCard.live")}
                      </span>
                    ) : null}
                  </div>
                  <p className="m-0 mt-1 truncate text-[0.8125rem] text-[var(--text-primary)]">
                    {truncateText(getRuntimeRowSummary(row), 104)}
                  </p>
                  <p className="m-0 mt-1 truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                    {truncateText(
                      row.environment?.workspace_path ||
                        row.environment?.branch_name ||
                        row.queue?.queue_name ||
                        row.source,
                      88,
                    )}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-right">
                  <p className="m-0 text-[0.6875rem] tabular-nums text-[var(--text-quaternary)]">
                    {row.updatedAt ? formatRelativeTime(row.updatedAt) : t("common.now")}
                  </p>
                  <ArrowRight className="h-3.5 w-3.5 text-[var(--text-quaternary)] transition-colors group-hover:text-[var(--text-secondary)]" />
                </div>
              </Link>
            );
          })
        )}
      </div>

      {selected.some((overview) => overview.incidents.length > 0) ? (
        <InlineAlert tone="warning" className="mt-4 py-2 text-[0.75rem]">
          {t("runtime.controlCard.backlogNotice")}
        </InlineAlert>
      ) : null}
    </section>
  );
});
