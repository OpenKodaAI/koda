"use client";

import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type {
  BotStats,
  CronJob,
  ExecutionSummary,
  SessionSummary,
  Task,
} from "@/lib/types";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { fetchControlPlaneDashboardJsonAllowError } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";

type BotDetailTab = "overview" | "tasks" | "sessions" | "cron";

function executionToTask(execution: ExecutionSummary): Task {
  return {
    id: execution.task_id,
    user_id: execution.user_id,
    chat_id: execution.chat_id,
    status: execution.status,
    query_text: execution.query_text,
    model: execution.model,
    work_dir: null,
    attempt: execution.attempt,
    max_attempts: execution.max_attempts,
    cost_usd: execution.cost_usd,
    error_message: execution.error_message,
    created_at: execution.created_at,
    started_at: execution.started_at,
    completed_at: execution.completed_at,
    session_id: execution.session_id,
  };
}

export function useBotDetail(
  botId: string | null,
  activeTab: BotDetailTab = "overview",
) {
  const { tl } = useAppI18n();
  const queryClient = useQueryClient();

  const statsQuery = useControlPlaneQuery<BotStats | null>({
    tier: "live",
    queryKey: ["dashboard", "bots", botId ?? "", "stats-modal"] as const,
    enabled: Boolean(botId),
    refetchInterval: 15_000,
    queryFn: async ({ signal }) => {
      const res = await fetchControlPlaneDashboardJsonAllowError<BotStats>(
        `/agents/${botId}/stats`,
        { signal, fallbackError: tl("Não foi possível carregar os dados do bot.") },
      );
      return res.ok ? res.data : null;
    },
  });

  const schedulesQuery = useControlPlaneQuery<CronJob[]>({
    tier: "detail",
    queryKey: queryKeys.dashboard.botSchedules(botId ?? ""),
    enabled: Boolean(botId),
    refetchInterval: 30_000,
    queryFn: async ({ signal }) => {
      const res = await fetchControlPlaneDashboardJsonAllowError<CronJob[]>(
        `/agents/${botId}/schedules`,
        { signal, fallbackError: tl("Não foi possível carregar os agendamentos do bot.") },
      );
      return res.ok && Array.isArray(res.data) ? res.data : [];
    },
  });

  const tasksQuery = useControlPlaneQuery<Task[]>({
    tier: "live",
    queryKey: queryKeys.dashboard.executions({ botIds: [botId ?? ""], limit: 50 }),
    enabled: Boolean(botId) && activeTab === "tasks",
    refetchInterval: 15_000,
    queryFn: async ({ signal }) => {
      const res = await fetchControlPlaneDashboardJsonAllowError<ExecutionSummary[]>(
        `/agents/${botId}/executions`,
        {
          signal,
          params: { limit: 50 },
          fallbackError: tl("Não foi possível carregar as execuções do bot."),
        },
      );
      return res.ok && Array.isArray(res.data)
        ? res.data.map(executionToTask)
        : [];
    },
  });

  const sessionsQuery = useControlPlaneQuery<SessionSummary[]>({
    tier: "live",
    queryKey: queryKeys.dashboard.sessions({ botId: botId ?? "", limit: 50 }),
    enabled: Boolean(botId) && activeTab === "sessions",
    refetchInterval: 15_000,
    queryFn: async ({ signal }) => {
      const res = await fetchControlPlaneDashboardJsonAllowError<SessionSummary[]>(
        `/agents/${botId}/sessions`,
        {
          signal,
          params: { limit: 50 },
          fallbackError: tl("Não foi possível carregar as sessões do bot."),
        },
      );
      return res.ok && Array.isArray(res.data) ? res.data : [];
    },
  });

  const refresh = useCallback(() => {
    if (!botId) return;
    void queryClient.invalidateQueries({
      queryKey: ["dashboard", "bots", botId],
    });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.dashboard.executions({ botIds: [botId], limit: 50 }),
    });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.dashboard.sessions({ botId, limit: 50 }),
    });
  }, [botId, queryClient]);

  const loading =
    statsQuery.isLoading || (schedulesQuery.isLoading && !schedulesQuery.data);
  const error =
    statsQuery.error?.message ?? schedulesQuery.error?.message ?? null;

  return {
    stats: statsQuery.data ?? null,
    tasks: tasksQuery.data ?? [],
    sessions: sessionsQuery.data ?? [],
    cronJobs: schedulesQuery.data ?? [],
    loading,
    refreshing: statsQuery.isFetching && !statsQuery.isLoading,
    error,
    refresh,
    lastUpdated: statsQuery.dataUpdatedAt || null,
  };
}
