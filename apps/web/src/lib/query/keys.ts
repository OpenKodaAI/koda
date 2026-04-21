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
  agentIds?: string[];
  status?: string;
  search?: string;
  sessionId?: string;
  limit?: number;
};

type CostsFilters = {
  agentIds?: string[];
  period?: "7d" | "30d" | "90d";
  groupBy?: CostGroupBy;
  model?: string;
  taskType?: string;
  language?: string;
};

type DlqFilters = {
  agentIds?: string[];
  retryFilter?: string;
  limit?: number;
};

type SessionsFilters = {
  agentId?: string;
  search?: string;
  limit?: number;
};

function normalizeStringArray(values?: string[]) {
  return [...(values ?? [])].filter(Boolean).sort();
}

export const queryKeys = {
  dashboard: {
    agentStatsSummary: () => ["dashboard", "agents", "summary"] as const,
    agentStatsDetail: (agentId: string) => ["dashboard", "agents", agentId, "stats"] as const,
    executions: (filters: ExecutionFilters) =>
      [
        "dashboard",
        "executions",
        {
          ...filters,
          agentIds: normalizeStringArray(filters.agentIds),
        },
      ] as const,
    executionDetail: (agentId: string, taskId: number, language?: string) =>
      ["dashboard", "executions", agentId, taskId, language ?? ""] as const,
    costs: (filters: CostsFilters) =>
      [
        "dashboard",
        "costs",
        {
          ...filters,
          agentIds: normalizeStringArray(filters.agentIds),
        },
      ] as const,
    dlq: (filters: DlqFilters) =>
      [
        "dashboard",
        "dlq",
        {
          ...filters,
          agentIds: normalizeStringArray(filters.agentIds),
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
    sessionDetail: (agentId: string, sessionId: string) =>
      ["dashboard", "sessions", agentId, sessionId] as const,
    agentSchedules: (agentId: string) =>
      ["dashboard", "agents", agentId, "schedules"] as const,
  },
  runtime: {
    overview: (agentId: string, language?: string) =>
      ["runtime", "overview", agentId, language ?? ""] as const,
    task: (agentId: string, taskId: number) =>
      ["runtime", "task", agentId, taskId] as const,
  },
  controlPlane: {
    workspacesTree: () => ["control-plane", "workspaces", "tree"] as const,
    agents: () => ["control-plane", "agents", "list"] as const,
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
