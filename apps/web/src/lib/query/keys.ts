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
  agentIds?: string[];
  agentId?: string;
  search?: string;
  limit?: number;
};

type ScheduleFilters = {
  agentIds?: string[];
  limit?: number;
};

type RuntimeRoomFilters = {
  agentIds?: string[];
  status?: string;
  search?: string;
  limit?: number;
};

function normalizeStringArray(values?: string[]) {
  return [...(values ?? [])].filter(Boolean).sort();
}

export const queryKeys = {
  dashboard: {
    agentStatsSummary: (recentTaskLimit?: number) =>
      ["dashboard", "agents", "summary", { recentTaskLimit: recentTaskLimit ?? 5 }] as const,
    agentStatsDetail: (agentId: string, recentTaskLimit?: number) =>
      ["dashboard", "agents", agentId, "stats", { recentTaskLimit: recentTaskLimit ?? 5 }] as const,
    executions: (filters: ExecutionFilters) =>
      [
        "dashboard",
        "executions",
        {
          ...filters,
          agentIds: normalizeStringArray(filters.agentIds),
        },
      ] as const,
    executionPages: (filters: ExecutionFilters) =>
      [
        "dashboard",
        "executions",
        "pages",
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
    dlqPages: (filters: DlqFilters) =>
      [
        "dashboard",
        "dlq",
        "pages",
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
          agentIds: normalizeStringArray(filters.agentIds),
        },
      ] as const,
    sessionPages: (filters: SessionsFilters) =>
      [
        "dashboard",
        "sessions",
        "pages",
        {
          ...filters,
          agentIds: normalizeStringArray(filters.agentIds),
        },
      ] as const,
    sessionDetail: (agentId: string, sessionId: string) =>
      ["dashboard", "sessions", agentId, sessionId] as const,
    sessionOlderPages: (
      agentId: string,
      sessionId: string,
      boundaryCursor: string,
      limit: number,
    ) => ["dashboard", "sessions", agentId, sessionId, "older", boundaryCursor, limit] as const,
    agentSchedules: (agentId: string) =>
      ["dashboard", "agents", agentId, "schedules"] as const,
    routineSchedules: (filters?: ScheduleFilters) =>
      [
        "dashboard",
        "routines",
        "schedules",
        {
          ...filters,
          agentIds: normalizeStringArray(filters?.agentIds),
        },
      ] as const,
    routineSchedulePages: (filters?: ScheduleFilters) =>
      [
        "dashboard",
        "routines",
        "schedules",
        "pages",
        {
          ...filters,
          agentIds: normalizeStringArray(filters?.agentIds),
        },
      ] as const,
    squadsOverview: (workspaceId?: string | null) =>
      ["dashboard", "squads", "overview", workspaceId ?? null] as const,
    squadThreads: (squadId: string, status?: string | null) =>
      ["dashboard", "squads", squadId, "threads", status ?? null] as const,
    squadActivity: (squadId: string) =>
      ["dashboard", "squads", squadId, "activity"] as const,
    squadThread: (threadId: string) =>
      ["dashboard", "squads", "threads", threadId] as const,
    squadThreadOlderPages: (
      threadId: string,
      boundaryCursor: string,
      limit: number,
    ) => ["dashboard", "squads", "threads", threadId, "older", boundaryCursor, limit] as const,
  },
  runtime: {
    overview: (agentId: string, language?: string) =>
      ["runtime", "overview", agentId, language ?? ""] as const,
    rooms: (filters: RuntimeRoomFilters) =>
      [
        "runtime",
        "rooms",
        {
          ...filters,
          agentIds: normalizeStringArray(filters.agentIds),
        },
      ] as const,
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
