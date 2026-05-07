export type SquadThreadCounts = {
  open: number;
  paused: number;
  completed: number;
  archived: number;
};

export type SquadTaskCounts = {
  pending: number;
  claimed: number;
  in_progress: number;
  blocked: number;
  done: number;
  failed: number;
  cancelled: number;
  escalated: number;
};

export type SquadOverviewItem = {
  squadId: string;
  workspaceId: string | null;
  coordinatorAgentId: string | null;
  threadCounts: SquadThreadCounts;
  taskCounts: SquadTaskCounts;
  memberCount: number;
  lastActiveAt: string | null;
  totalCostUsd: string;
};

export type SquadOverviewResponse = {
  items: SquadOverviewItem[];
  count: number;
  available: boolean;
};

export type SquadThreadSummary = {
  id: string;
  workspaceId: string;
  squadId: string;
  title: string;
  status: string;
  coordinatorAgentId: string | null;
  currentOwnerAgentId: string | null;
  telegramChatId: number | null;
  telegramMessageThreadId: number | null;
  costUsdAccum: string;
  createdAt: string | null;
  updatedAt: string | null;
  completedAt: string | null;
};

export type SquadThreadsResponse = {
  items: SquadThreadSummary[];
  count: number;
  available: boolean;
};

export type SquadActivityEntry = {
  timestamp: string | null;
  source: string;
  eventType: string;
  actor: string | null;
  summary: string;
  threadId: string | null;
  payload: Record<string, unknown>;
};

export type SquadActivityResponse = {
  items: SquadActivityEntry[];
  count: number;
  available: boolean;
};

export type SquadThreadOverviewResponse = {
  thread: {
    id: string;
    workspaceId: string;
    squadId: string;
    title: string;
    status: string;
    ownerUserId: number | null;
    coordinatorAgentId: string | null;
    currentOwnerAgentId: string | null;
    telegramChatId: number | null;
    telegramMessageThreadId: number | null;
    budgetUsdCap: string | null;
    costUsdAccum: string;
    createdAt: string | null;
    updatedAt: string | null;
  };
  coordinatorAgentId: string | null;
  participants: Array<{
    agentId: string;
    role: string;
    joinedAt: string | null;
    leftAt: string | null;
  }>;
  recentMessages: Array<{
    id: number;
    from: string | null;
    to: string | null;
    content: string;
    type: string;
    metadata: Record<string, unknown>;
    createdAt: string | null;
  }>;
  activeTasks: Array<{
    id: string;
    title: string;
    status: string;
    assignedAgentId: string | null;
    assignerAgentId: string;
    kind: string;
    version: number;
  }>;
  openTaskCount: number;
  doneTaskCount: number;
};

export function formatRelativeTimestamp(value: string | null): string {
  if (!value) return "—";
  const ts = new Date(value);
  if (Number.isNaN(ts.getTime())) return "—";
  const diffMs = Date.now() - ts.getTime();
  if (diffMs < 0) return "now";
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo`;
  return `${Math.floor(months / 12)}y`;
}
