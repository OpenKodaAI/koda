import type {
  CostGroupBy,
  CostInsightsResponse,
  DLQEntry,
  ExecutionDetail,
  ExecutionSummary,
  SessionDetail,
  SessionSummary,
} from "@/lib/types";

type ExecutionFilters = {
  botIds?: string[];
  status?: string;
  search?: string;
  limit?: number;
};

type CostsFilters = {
  botIds?: string[];
  period?: "7d" | "30d" | "90d";
  groupBy?: CostGroupBy;
  model?: string;
  taskType?: string;
  language?: string;
};

type DlqFilters = {
  botIds?: string[];
  retryFilter?: string;
  limit?: number;
};

type SessionsFilters = {
  botId?: string;
  search?: string;
  limit?: number;
};

function normalizeStringArray(values?: string[]) {
  return [...(values ?? [])].filter(Boolean).sort();
}

export const queryKeys = {
  dashboard: {
    botStatsSummary: () => ["dashboard", "bots", "summary"] as const,
    botStatsDetail: (botId: string) => ["dashboard", "bots", botId, "stats"] as const,
    executions: (filters: ExecutionFilters) =>
      [
        "dashboard",
        "executions",
        {
          ...filters,
          botIds: normalizeStringArray(filters.botIds),
        },
      ] as const,
    executionDetail: (botId: string, taskId: number, language?: string) =>
      ["dashboard", "executions", botId, taskId, language ?? ""] as const,
    costs: (filters: CostsFilters) =>
      [
        "dashboard",
        "costs",
        {
          ...filters,
          botIds: normalizeStringArray(filters.botIds),
        },
      ] as const,
    dlq: (filters: DlqFilters) =>
      [
        "dashboard",
        "dlq",
        {
          ...filters,
          botIds: normalizeStringArray(filters.botIds),
        },
      ] as const,
    sessions: (filters: SessionsFilters) =>
      [
        "dashboard",
        "sessions",
        {
          ...filters,
        },
      ] as const,
    sessionDetail: (botId: string, sessionId: string) =>
      ["dashboard", "sessions", botId, sessionId] as const,
  },
  runtime: {
    overview: (botId: string, language?: string) =>
      ["runtime", "overview", botId, language ?? ""] as const,
  },
};

export type QueryKeyMap = {
  executions: ExecutionSummary[];
  executionDetail: ExecutionDetail;
  costs: CostInsightsResponse;
  dlq: DLQEntry[];
  sessions: SessionSummary[];
  sessionDetail: SessionDetail;
};
