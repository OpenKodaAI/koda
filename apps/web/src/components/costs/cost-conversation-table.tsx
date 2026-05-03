"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { getAgentColor, getAgentLabel } from "@/lib/agent-constants";
import { getSemanticTextStyle, getSemanticTone, getSemanticVars } from "@/lib/theme-semantic";
import type { CostConversationRow } from "@/lib/types";
import { cn, formatCost, formatRelativeTime, truncateText } from "@/lib/utils";

interface CostConversationTableProps {
  rows: CostConversationRow[];
  className?: string;
}

function getStatusText(
  status: CostConversationRow["status"],
  tl: (value: string, options?: Record<string, unknown>) => string
) {
  switch (status) {
    case "resolved":
      return tl("Resolvida");
    case "running":
      return tl("Executando");
    case "failed":
      return tl("Falhou");
    case "queued":
      return tl("Na fila");
    default:
      return tl("Aberta");
  }
}

function getTaskTypeText(
  taskType: string,
  tl: (value: string, options?: Record<string, unknown>) => string
) {
  switch (taskType) {
    case "reply":
      return tl("Resposta");
    case "research":
      return tl("Pesquisa");
    case "summarization":
      return tl("Resumo");
    case "jira_update":
      return tl("Jira");
    case "triage":
      return tl("Triagem");
    case "memory_lookup":
      return tl("Memória");
    case "content_generation":
      return tl("Geração");
    case "other":
      return tl("Outro");
    default:
      return taskType;
  }
}

function getStatusTone(status: CostConversationRow["status"]) {
  switch (status) {
    case "resolved":
      return getSemanticTone("completed");
    case "running":
      return getSemanticTone("running");
    case "failed":
      return getSemanticTone("failed");
    case "queued":
      return getSemanticTone("queued");
    default:
      return "neutral";
  }
}

export function CostConversationTable({ rows, className }: CostConversationTableProps) {
  const { t, tl } = useAppI18n();
  return (
    <section
      className={cn(
        "overflow-hidden rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)]",
        className
      )}
    >
      <div className="flex min-w-0 items-center justify-between gap-4 border-b border-[var(--border-subtle)] px-4 py-3 sm:px-5">
        <div className="min-w-0">
          <p className="eyebrow truncate">{t("costs.ledger.eyebrow")}</p>
          <h3 className="mt-1 truncate text-[var(--font-size-md)] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
            {t("costs.ledger.title")}
          </h3>
        </div>
        <span className="shrink-0 font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
          {t("costs.ledger.count", { count: rows.length })}
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="empty-state px-5 py-10">
          <p className="empty-state-text truncate">
            {t("costs.page.noConversations", {
              defaultValue: "No conversations in the current filter.",
            })}
          </p>
        </div>
      ) : (
        <div className="divide-y divide-[var(--border-subtle)]">
          {rows.map((row) => {
            const tone = getStatusTone(row.status);
            const toneVars = getSemanticVars(tone);

            return (
              <article
                key={`${row.agent_id}-${row.session_id}`}
                className="grid min-w-0 gap-3 px-4 py-3 sm:px-5 lg:grid-cols-[minmax(0,1fr)_112px] lg:items-center"
              >
                <div className="min-w-0">
                  <div className="flex min-w-0 items-center gap-3">
                    <p className="min-w-0 truncate text-[0.875rem] font-medium text-[var(--text-primary)]">
                      {row.name || truncateText(row.session_id, 42)}
                    </p>
                    <span
                      className="inline-flex shrink-0 items-center gap-1.5 text-[12px] font-medium"
                      style={{ color: getAgentColor(row.agent_id) }}
                    >
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: getAgentColor(row.agent_id) }}
                      />
                      <span className="max-w-[120px] truncate">{getAgentLabel(row.agent_id)}</span>
                    </span>
                    <span className="inline-flex shrink-0 items-center gap-1.5 text-[12px]" style={getSemanticTextStyle(tone)}>
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{
                          backgroundColor: toneVars.dot,
                        }}
                      />
                      {t(`costs.page.conversationStatus.${row.status}`, {
                        defaultValue: getStatusText(row.status, tl),
                      })}
                    </span>
                  </div>

                  <p className="mt-1 truncate text-[13px] text-[var(--text-secondary)]">
                    {row.latest_message_preview ||
                      t("costs.page.noRecentPreview", { defaultValue: "No recent preview" })}
                  </p>

                  <div className="mt-2 flex min-w-0 items-center gap-3 overflow-hidden text-[12px] text-[var(--text-tertiary)]">
                    <span className="shrink-0 truncate">
                      {row.dominant_model
                        ? truncateText(row.dominant_model, 24)
                        : t("costs.page.noModel", { defaultValue: "No model" })}
                    </span>
                    <span className="min-w-0 truncate">
                      {row.task_type_mix.length > 0
                        ? row.task_type_mix.map((taskType) => getTaskTypeText(taskType, tl)).join(" · ")
                        : t("costs.page.noDominantOrigin", { defaultValue: "No dominant origin" })}
                    </span>
                    <span className="shrink-0">
                      {t("costs.page.queriesCount", {
                        defaultValue: "{{count}} queries",
                        count: row.query_count,
                      })}
                    </span>
                    <span className="shrink-0">
                      {t("costs.page.executionsCount", {
                        defaultValue: "{{count}} executions",
                        count: row.execution_count,
                      })}
                    </span>
                    <span className="shrink-0">{formatRelativeTime(row.last_activity_at)}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between gap-3 text-left lg:block lg:text-right">
                  <p className="font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)] lg:mb-1">
                    {t("common.cost")}
                  </p>
                  <p className="font-mono text-[0.9375rem] font-medium text-[var(--text-primary)]">
                    {formatCost(row.cost_usd)}
                  </p>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
