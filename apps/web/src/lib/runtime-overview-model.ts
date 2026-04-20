import type {
  RuntimeEnvironment,
  RuntimeOverview,
  RuntimeQueueItem,
} from "@/lib/runtime-types";

export type RuntimeRoomFilter = "all" | "active" | "retained" | "recovery";

export interface RuntimeRoomRow {
  agentId: string;
  taskId: number;
  queryText: string;
  source: "environment" | "queue";
  status: string;
  phase: string;
  updatedAt: string | null;
  environment: RuntimeEnvironment | null;
  queue: RuntimeQueueItem | null;
}

function sortRuntimeRoomRows(rows: RuntimeRoomRow[]) {
  return rows.sort((left, right) => {
    const leftTime = left.updatedAt ? new Date(left.updatedAt).getTime() : 0;
    const rightTime = right.updatedAt ? new Date(right.updatedAt).getTime() : 0;
    return rightTime - leftTime;
  });
}

export function buildRuntimeRoomRows(items: RuntimeOverview[]) {
  const rows: RuntimeRoomRow[] = [];

  items.forEach((overview) => {
    const environmentTaskIds = new Set<number>();

    overview.environments.forEach((environment) => {
      const queue = overview.queues.find((item) => item.task_id === environment.task_id) ?? null;
      environmentTaskIds.add(environment.task_id);
      rows.push({
        agentId: overview.agentId,
        taskId: environment.task_id,
        queryText: String(queue?.query_text || ""),
        source: "environment",
        status: String(environment.status || "unknown"),
        phase: String(environment.current_phase || environment.status || "unknown"),
        updatedAt:
          environment.updated_at || environment.last_heartbeat_at || environment.created_at || null,
        environment,
        queue,
      });
    });

    overview.queues.forEach((queue) => {
      if (environmentTaskIds.has(queue.task_id)) return;
      rows.push({
        agentId: overview.agentId,
        taskId: queue.task_id,
        queryText: String(queue.query_text || ""),
        source: "queue",
        status: String(queue.status || "queued"),
        phase: String(queue.status || "queued"),
        updatedAt: queue.updated_at || queue.queued_at || null,
        environment: null,
        queue,
      });
    });
  });

  return sortRuntimeRoomRows(rows);
}

export function matchesRuntimeRoomFilter(
  row: RuntimeRoomRow,
  filter: RuntimeRoomFilter
) {
  if (filter === "all") return true;
  if (filter === "active") {
    return ["active", "running", "queued", "cleaning", "retrying"].includes(row.status);
  }
  if (filter === "retained") {
    return row.status === "retained";
  }
  return row.phase.includes("recover") || row.status.includes("failed");
}

export function getRuntimeRowSummary(row: RuntimeRoomRow) {
  return (
    row.queryText ||
    String(row.environment?.workspace_path || row.environment?.branch_name || row.phase || "Runtime task")
  );
}
