"use client";

import { useCallback } from "react";
import type {
  BotStats,
  CronJob,
  ExecutionSummary,
  SessionSummary,
  Task,
} from "@/lib/types";
import { useAsyncResource } from "@/hooks/use-async-resource";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { fetchControlPlaneDashboardJsonAllowError } from "@/lib/control-plane-dashboard";

interface BotDetailState {
  stats: BotStats | null;
  tasks: Task[];
  sessions: SessionSummary[];
  cronJobs: CronJob[];
  loading: boolean;
  error: string | null;
}

const INITIAL_STATE: BotDetailState = {
  stats: null,
  tasks: [],
  sessions: [],
  cronJobs: [],
  loading: true,
  error: null,
};

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

export function useBotDetail(botId: string | null, refreshInterval: number = 15000) {
  const { tl } = useAppI18n();
  const fetcher = useCallback(async (signal: AbortSignal) => {
    if (!botId) {
      return {
        stats: null,
        tasks: [],
        sessions: [],
        cronJobs: [],
        loadError: null,
      };
    }

    const [statsRes, tasksRes, sessionsRes, cronRes] = await Promise.all([
      fetchControlPlaneDashboardJsonAllowError<BotStats>(`/agents/${botId}/stats`, {
        signal,
        fallbackError: tl("Não foi possível carregar os dados do bot."),
      }),
      fetchControlPlaneDashboardJsonAllowError<ExecutionSummary[]>(
        `/agents/${botId}/executions`,
        {
          signal,
          params: { limit: 50 },
          fallbackError: tl("Não foi possível carregar as execuções do bot."),
        },
      ),
      fetchControlPlaneDashboardJsonAllowError<SessionSummary[]>(
        `/agents/${botId}/sessions`,
        {
          signal,
          params: { limit: 50 },
          fallbackError: tl("Não foi possível carregar as sessões do bot."),
        },
      ),
      fetchControlPlaneDashboardJsonAllowError<CronJob[]>(
        `/agents/${botId}/schedules`,
        {
          signal,
          fallbackError: tl("Não foi possível carregar os agendamentos do bot."),
        },
      ),
    ]);

    return {
      stats: statsRes.ok ? statsRes.data : null,
      tasks:
        tasksRes.ok && Array.isArray(tasksRes.data)
          ? tasksRes.data.map(executionToTask)
          : [],
      sessions:
        sessionsRes.ok && Array.isArray(sessionsRes.data)
          ? sessionsRes.data
          : [],
      cronJobs:
        cronRes.ok && Array.isArray(cronRes.data)
          ? cronRes.data
          : [],
      loadError:
        statsRes.error ??
        tasksRes.error ??
        sessionsRes.error ??
        cronRes.error,
    };
  }, [botId, tl]);

  const resource = useAsyncResource<
    Omit<BotDetailState, "loading" | "error"> & { loadError: string | null }
  >({
    enabled: Boolean(botId),
    initialData: null,
    pollIntervalMs: botId ? refreshInterval : null,
    fetcher,
  });

  return {
    stats: resource.data?.stats ?? INITIAL_STATE.stats,
    tasks: resource.data?.tasks ?? INITIAL_STATE.tasks,
    sessions: resource.data?.sessions ?? INITIAL_STATE.sessions,
    cronJobs: resource.data?.cronJobs ?? INITIAL_STATE.cronJobs,
    loading: resource.initialLoading,
    refreshing: resource.refreshing,
    error: resource.error ?? resource.data?.loadError ?? null,
    refresh: resource.refresh,
    lastUpdated: resource.lastUpdated,
  };
}
