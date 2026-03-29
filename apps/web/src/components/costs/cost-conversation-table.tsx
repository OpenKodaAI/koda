"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";
import { getBotColor, getBotLabel } from "@/lib/bot-constants";
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
        "overflow-hidden rounded-[18px] border border-[rgba(255,255,255,0.06)] bg-[rgba(8,8,9,0.92)]",
        className
      )}
      style={{
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.025), 0 18px 42px rgba(0,0,0,0.18)",
      }}
    >
      <div className="flex items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.06)] px-5 py-4">
        <div>
          <p className="eyebrow">{t("costs.ledger.eyebrow")}</p>
          <h3 className="mt-2 text-[1.1rem] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
            {t("costs.ledger.title")}
          </h3>
        </div>
        <span className="text-[11px] text-[rgba(255,255,255,0.42)]">
          {t("costs.ledger.count", { count: rows.length })}
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="empty-state px-5 py-10">
          <p className="empty-state-text">
            {t("costs.page.noConversations", {
              defaultValue: "No conversations in the current filter.",
            })}
          </p>
        </div>
      ) : (
        <div className="divide-y divide-[rgba(255,255,255,0.06)]">
          {rows.map((row) => {
            const tone = getStatusTone(row.status);
            const toneVars = getSemanticVars(tone);

            return (
              <article
                key={`${row.bot_id}-${row.session_id}`}
                className="grid gap-4 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_120px] lg:items-start"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <p className="truncate text-[15px] font-semibold text-[var(--text-primary)]">
                      {row.name || truncateText(row.session_id, 42)}
                    </p>
                    <span
                      className="inline-flex items-center gap-2 text-[12px] font-medium"
                      style={{ color: getBotColor(row.bot_id) }}
                    >
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: getBotColor(row.bot_id) }}
                      />
                      {getBotLabel(row.bot_id)}
                    </span>
                    <span className="inline-flex items-center gap-2 text-[12px]" style={getSemanticTextStyle(tone)}>
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{
                          backgroundColor: toneVars.dot,
                          boxShadow: `0 0 0 4px color-mix(in srgb, ${toneVars.dot} 16%, transparent)`,
                        }}
                      />
                      {t(`costs.page.conversationStatus.${row.status}`, {
                        defaultValue: getStatusText(row.status, tl),
                      })}
                    </span>
                  </div>

                  <p className="mt-2 line-clamp-1 text-[13px] leading-5 text-[var(--text-secondary)]">
                    {row.latest_message_preview ||
                      t("costs.page.noRecentPreview", { defaultValue: "No recent preview" })}
                  </p>

                  <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-[rgba(255,255,255,0.46)]">
                    <span>
                      {row.dominant_model
                        ? truncateText(row.dominant_model, 24)
                        : t("costs.page.noModel", { defaultValue: "No model" })}
                    </span>
                    <span>
                      {row.task_type_mix.length > 0
                        ? row.task_type_mix.map((taskType) => getTaskTypeText(taskType, tl)).join(" · ")
                        : t("costs.page.noDominantOrigin", { defaultValue: "No dominant origin" })}
                    </span>
                    <span>
                      {t("costs.page.queriesCount", {
                        defaultValue: "{{count}} queries",
                        count: row.query_count,
                      })}
                    </span>
                    <span>
                      {t("costs.page.executionsCount", {
                        defaultValue: "{{count}} executions",
                        count: row.execution_count,
                      })}
                    </span>
                    <span>{formatRelativeTime(row.last_activity_at)}</span>
                  </div>
                </div>

                <div className="text-left lg:text-right">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[rgba(255,255,255,0.32)]">
                    {t("common.cost")}
                  </p>
                  <p className="mt-2 font-mono text-[1.2rem] font-medium text-[var(--text-primary)]">
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
