"use client";

import { DetailDatum, DetailGrid } from "@/components/ui/detail-group";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { SessionDetail, SessionSummary } from "@/lib/types";
import { formatCost, formatRelativeTime } from "@/lib/utils";

interface ContextSummaryProps {
  summary: SessionSummary;
  detail: SessionDetail;
  agentLabel: string | null;
  agentColor: string | null;
  modelLabel: string | null;
}

export function ContextSummary({
  summary,
  detail,
  agentLabel,
  agentColor,
  modelLabel,
}: ContextSummaryProps) {
  const { t } = useAppI18n();

  return (
    <section className="px-5 py-5">
      <h4 className="m-0 mb-3 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {t("sessions.context.summaryLabel", { defaultValue: "Summary" })}
      </h4>
      <DetailGrid columns={2}>
        <DetailDatum
          label={t("sessions.detail.agent", { defaultValue: "Agent" })}
          value={
            agentLabel ? (
              <span className="inline-flex min-w-0 items-center gap-1.5">
                <span
                  aria-hidden
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: agentColor ?? "var(--accent)" }}
                />
                <span className="truncate">{agentLabel}</span>
              </span>
            ) : (
              "—"
            )
          }
        />
        <DetailDatum
          label={t("sessions.detail.model", { defaultValue: "Model" })}
          value={
            modelLabel ? (
              <span className="font-mono text-[0.8125rem]">{modelLabel}</span>
            ) : (
              "—"
            )
          }
        />
        <DetailDatum
          label={t("sessions.context.createdAt", { defaultValue: "Created" })}
          value={summary.created_at ? formatRelativeTime(summary.created_at) : "—"}
        />
        <DetailDatum
          label={t("sessions.context.lastActivity", { defaultValue: "Last activity" })}
          value={summary.last_activity_at ? formatRelativeTime(summary.last_activity_at) : "—"}
        />
        <DetailDatum
          label={t("sessions.context.messages", { defaultValue: "Messages" })}
          value={detail.totals.messages}
        />
        <DetailDatum
          label={t("sessions.context.executions", { defaultValue: "Executions" })}
          value={detail.totals.executions}
        />
        <DetailDatum
          label={t("sessions.context.tools", { defaultValue: "Tools" })}
          value={detail.totals.tools}
        />
        <DetailDatum
          label={t("sessions.context.cost", { defaultValue: "Cost" })}
          value={formatCost(detail.totals.cost_usd)}
        />
      </DetailGrid>
    </section>
  );
}
