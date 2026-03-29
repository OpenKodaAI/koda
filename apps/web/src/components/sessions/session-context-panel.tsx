"use client";

import { Info, MessageSquareText } from "lucide-react";
import { StatusIndicator } from "@/components/dashboard/status-indicator";
import { useAppI18n } from "@/hooks/use-app-i18n";
import type { ExecutionSummary, SessionDetail, SessionSummary } from "@/lib/types";
import { formatCost, formatRelativeTime, truncateText } from "@/lib/utils";

function dedupeExecutions(detail: SessionDetail | null) {
  if (!detail) return [];
  const byId = new Map<number, ExecutionSummary>();
  for (const execution of detail.orphan_executions) {
    byId.set(execution.task_id, execution);
  }
  for (const message of detail.messages) {
    if (message.linked_execution) {
      byId.set(message.linked_execution.task_id, message.linked_execution);
    }
  }
  return [...byId.values()].sort((left, right) => {
    const leftTime = new Date(left.completed_at || left.started_at || left.created_at).getTime();
    const rightTime = new Date(right.completed_at || right.started_at || right.created_at).getTime();
    return rightTime - leftTime;
  });
}

function MetaBlock({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div className="rounded-[1.05rem] border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.025)] px-3.5 py-3">
      <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">{label}</p>
      <p className="mt-2 text-[15px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
        {value ?? "—"}
      </p>
    </div>
  );
}

interface SessionContextPanelProps {
  detail: SessionDetail | null;
  summary: SessionSummary | null;
  className?: string;
}

export function SessionContextPanel({
  detail,
  summary,
  className,
}: SessionContextPanelProps) {
  const { t } = useAppI18n();
  const executions = dedupeExecutions(detail).slice(0, 6);

  if (!summary || !detail) {
    return (
      <aside
        className={`flex h-full min-h-0 flex-col border-l border-[rgba(255,255,255,0.06)] bg-[#0d0e12] ${className ?? ""}`}
      >
        <div className="flex h-full flex-col items-center justify-center px-6 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-[1.35rem] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)]">
            <Info className="h-6 w-6 text-[var(--text-tertiary)]" />
          </div>
          <p className="mt-4 text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
            {t("sessions.context.emptyTitle", { defaultValue: "Conversation details" })}
          </p>
          <p className="mt-2 max-w-xs text-sm leading-6 text-[var(--text-secondary)]">
            {t("sessions.context.emptyDescription", {
              defaultValue: "Choose a conversation to inspect status, activity, linked executions and identifiers.",
            })}
          </p>
        </div>
      </aside>
    );
  }

  return (
    <aside
      className={`flex h-full min-h-0 flex-col border-l border-[rgba(255,255,255,0.06)] bg-[#0d0e12] ${className ?? ""}`}
    >
      <div className="border-b border-[rgba(255,255,255,0.06)] px-5 py-4">
        <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
          {t("sessions.page.conversationInfo", { defaultValue: "Conversation info" })}
        </p>
        <h3 className="mt-2 truncate text-[1rem] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
          {summary.name || truncateText(summary.session_id, 28)}
        </h3>
        <div className="mt-2 flex items-center gap-2 text-[12px] text-[var(--text-tertiary)]">
          {summary.latest_status ? <StatusIndicator status={summary.latest_status} /> : null}
          <span>{summary.latest_status || t("sessions.detail.sessionInProgress")}</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <div className="grid grid-cols-2 gap-3">
          <MetaBlock
            label={t("sessions.context.messages", { defaultValue: "Messages" })}
            value={detail.totals.messages}
          />
          <MetaBlock
            label={t("sessions.context.executions", { defaultValue: "Executions" })}
            value={detail.totals.executions}
          />
          <MetaBlock
            label={t("sessions.context.tools", { defaultValue: "Tools" })}
            value={detail.totals.tools}
          />
          <MetaBlock
            label={t("sessions.context.cost", { defaultValue: "Cost" })}
            value={formatCost(detail.totals.cost_usd)}
          />
        </div>

        <div className="mt-5 space-y-3 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.022)] p-4">
          <div>
            <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
              {t("sessions.context.createdAt", { defaultValue: "Created" })}
            </p>
            <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
              {summary.created_at ? formatRelativeTime(summary.created_at) : "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
              {t("sessions.context.lastActivity", { defaultValue: "Last activity" })}
            </p>
            <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
              {summary.last_activity_at ? formatRelativeTime(summary.last_activity_at) : "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
              {t("sessions.context.sessionId", { defaultValue: "Session ID" })}
            </p>
            <p className="mt-1 break-all font-mono text-[12px] text-[var(--text-secondary)]">
              {summary.session_id}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-quaternary)]">
              {t("sessions.context.userId", { defaultValue: "User ID" })}
            </p>
            <p className="mt-1 font-mono text-[12px] text-[var(--text-secondary)]">
              {summary.user_id ?? "—"}
            </p>
          </div>
        </div>

        <div className="mt-5">
          <div className="mb-3 flex items-center gap-2">
            <MessageSquareText className="h-4 w-4 text-[var(--text-tertiary)]" />
            <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-quaternary)]">
              {t("sessions.context.recentExecutions", { defaultValue: "Recent executions" })}
            </p>
          </div>

          {executions.length === 0 ? (
            <div className="rounded-[1.1rem] border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] px-4 py-4 text-sm text-[var(--text-tertiary)]">
              {t("sessions.context.noExecutions", { defaultValue: "No linked executions yet." })}
            </div>
          ) : (
            <div className="space-y-2.5">
              {executions.map((execution) => (
                <div
                  key={execution.task_id}
                  className="rounded-[1.05rem] border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.022)] px-3.5 py-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium text-[var(--text-primary)]">
                        #{execution.task_id} {execution.query_text ? truncateText(execution.query_text, 40) : "Execution"}
                      </p>
                      <p className="mt-1 truncate text-[12px] text-[var(--text-tertiary)]">
                        {execution.model || "—"} • {formatRelativeTime(execution.completed_at || execution.started_at || execution.created_at)}
                      </p>
                      {(execution.feedback_status || execution.retrieval_strategy || execution.answer_gate_status) ? (
                        <p className="mt-1 truncate text-[11px] text-[var(--text-quaternary)]">
                          {execution.feedback_status ? `feedback: ${execution.feedback_status}` : ""}
                          {execution.feedback_status && execution.retrieval_strategy ? " • " : ""}
                          {execution.retrieval_strategy ? `provenance: ${execution.retrieval_strategy}` : ""}
                          {(execution.feedback_status || execution.retrieval_strategy) && execution.answer_gate_status ? " • " : ""}
                          {execution.answer_gate_status ? `gate: ${execution.answer_gate_status}` : ""}
                        </p>
                      ) : null}
                    </div>
                    <span className="shrink-0 text-[12px] font-semibold text-[var(--text-primary)]">
                      {formatCost(execution.cost_usd)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
