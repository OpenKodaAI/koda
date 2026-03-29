import "server-only";

import {
  getControlPlaneBots,
  getControlPlaneSystemSettings,
} from "@/lib/control-plane";
import {
  getRuntimeOverview,
  getRuntimeTaskBundle,
  listRuntimeTaskSnapshots,
} from "@/lib/runtime-api";
import { buildRuntimeRoomRows, type RuntimeRoomRow } from "@/lib/runtime-overview-model";
import type {
  CostComparison,
  CostConversationRow,
  CostInsightsResponse,
  CostOverview,
  CostPeakBucket,
  CostTimePoint,
  CronJob,
  DLQEntry,
  ExecutionArtifact,
  ExecutionDetail,
  ExecutionSummary,
  SessionDetail,
  SessionMessage,
  SessionSummary,
  Task,
  BotStats,
} from "@/lib/types";
import type {
  RuntimeEvent,
  RuntimeGuardrailHit,
  RuntimeTaskBundle,
  RuntimeTaskDetail,
  RuntimeWarning,
} from "@/lib/runtime-types";

type RuntimeTaskSnapshotEnvelope = {
  task?: RuntimeTaskDetail;
  warnings?: RuntimeWarning[];
  guardrails?: RuntimeGuardrailHit[];
  environment?: Record<string, unknown> | null;
};

type BotRuntimeCollection = {
  overview: Awaited<ReturnType<typeof getRuntimeOverview>>;
  rows: RuntimeRoomRow[];
  snapshots: Map<number, RuntimeTaskSnapshotEnvelope>;
};

function toIsoDay(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 10);
}

function toTimestamp(value: string | null | undefined) {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function computeDurationMs(task: RuntimeTaskDetail) {
  const startedAt = task.started_at || task.created_at;
  const completedAt = task.completed_at;
  if (!startedAt || !completedAt) return null;
  const diff = toTimestamp(completedAt) - toTimestamp(startedAt);
  return diff >= 0 ? diff : null;
}

function toRuntimeTask(row: RuntimeRoomRow, task: RuntimeTaskDetail): Task {
  return {
    id: Number(task.id ?? row.taskId),
    user_id: Number(task.user_id ?? row.queue?.user_id ?? row.environment?.user_id ?? 0),
    chat_id: Number(task.chat_id ?? row.queue?.chat_id ?? row.environment?.chat_id ?? 0),
    status: (String(task.status || row.status || "queued") as Task["status"]),
    query_text: String(task.query_text || row.queryText || "") || null,
    model: typeof task.model === "string" ? task.model : null,
    work_dir: typeof task.work_dir === "string" ? task.work_dir : null,
    attempt: Number(task.attempt ?? 1),
    max_attempts: Number(task.max_attempts ?? 1),
    cost_usd: Number(task.cost_usd ?? 0),
    error_message: typeof task.error_message === "string" ? task.error_message : null,
    created_at: String(task.created_at || row.updatedAt || new Date().toISOString()),
    started_at: typeof task.started_at === "string" ? task.started_at : null,
    completed_at: typeof task.completed_at === "string" ? task.completed_at : null,
    session_id: typeof task.session_id === "string" ? task.session_id : null,
  };
}

function toExecutionSummary(botId: string, row: RuntimeRoomRow, task: RuntimeTaskDetail, warnings: RuntimeWarning[] = []): ExecutionSummary {
  const legacyTask = toRuntimeTask(row, task);
  return {
    task_id: legacyTask.id,
    bot_id: botId,
    status: legacyTask.status,
    query_text: legacyTask.query_text,
    model: legacyTask.model,
    session_id: legacyTask.session_id,
    user_id: legacyTask.user_id,
    chat_id: legacyTask.chat_id,
    created_at: legacyTask.created_at,
    started_at: legacyTask.started_at,
    completed_at: legacyTask.completed_at,
    cost_usd: legacyTask.cost_usd,
    duration_ms: computeDurationMs(task),
    attempt: legacyTask.attempt,
    max_attempts: legacyTask.max_attempts,
    has_rich_trace: false,
    trace_source: "missing",
    tool_count: 0,
    warning_count: warnings.length,
    stop_reason:
      typeof task.current_phase === "string"
        ? task.current_phase
        : typeof task.status === "string"
          ? task.status
          : null,
    error_message: legacyTask.error_message,
  };
}

function filterRows(
  rows: RuntimeRoomRow[],
  {
    search,
    status,
    limit,
  }: { search?: string | null; status?: string | null; limit?: number | null },
) {
  const normalizedSearch = search?.trim().toLowerCase() ?? "";
  const normalizedStatus = status?.trim().toLowerCase() ?? "";

  let filtered = rows.filter((row) => {
    if (normalizedStatus && String(row.status || "").toLowerCase() !== normalizedStatus) {
      return false;
    }
    if (!normalizedSearch) {
      return true;
    }
    const haystack = [
      row.queryText,
      row.environment?.workspace_path,
      row.environment?.branch_name,
      row.phase,
      row.status,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(normalizedSearch);
  });

  if (limit && limit > 0) {
    filtered = filtered.slice(0, limit);
  }

  return filtered;
}

async function getBotRuntimeCollection(
  botId: string,
  options: { search?: string | null; status?: string | null; limit?: number | null } = {},
): Promise<BotRuntimeCollection> {
  const overview = await getRuntimeOverview(botId);
  const rows = filterRows(buildRuntimeRoomRows([overview]), options);
  const snapshots = await listRuntimeTaskSnapshots(
    botId,
    rows.map((row) => row.taskId),
  );
  return { overview, rows, snapshots };
}

function buildEmptyBotStats(botId: string): BotStats {
  return {
    botId,
    totalTasks: 0,
    activeTasks: 0,
    completedTasks: 0,
    failedTasks: 0,
    queuedTasks: 0,
    totalQueries: 0,
    totalCost: 0,
    todayCost: 0,
    dbExists: false,
    recentTasks: [],
    dailyCosts: [],
  };
}

export async function getOperationalBotStats(botId: string): Promise<BotStats> {
  try {
    const { overview, rows, snapshots } = await getBotRuntimeCollection(botId, {
      limit: 50,
    });
    const tasks = rows
      .map((row) => {
        const snapshot = snapshots.get(row.taskId);
        const task = snapshot?.task;
        if (!task) return null;
        return {
          runtime: toRuntimeTask(row, task),
          warnings: snapshot?.warnings ?? [],
        };
      })
      .filter((item): item is { runtime: Task; warnings: RuntimeWarning[] } => Boolean(item))
      .sort((left, right) => toTimestamp(right.runtime.created_at) - toTimestamp(left.runtime.created_at));

    const today = new Date().toISOString().slice(0, 10);
    const dailyCostMap = new Map<string, number>();
    let totalCost = 0;
    let todayCost = 0;

    for (const item of tasks) {
      totalCost += item.runtime.cost_usd;
      const day = toIsoDay(item.runtime.created_at);
      if (day) {
        dailyCostMap.set(day, (dailyCostMap.get(day) ?? 0) + item.runtime.cost_usd);
        if (day === today) {
          todayCost += item.runtime.cost_usd;
        }
      }
    }

    return {
      botId,
      totalTasks: tasks.length,
      activeTasks: overview.snapshot?.active_environments ?? 0,
      completedTasks: tasks.filter((task) => task.runtime.status === "completed").length,
      failedTasks: tasks.filter((task) => task.runtime.status === "failed").length,
      queuedTasks: tasks.filter((task) =>
        ["queued", "retrying", "running"].includes(task.runtime.status),
      ).length,
      totalQueries: tasks.filter((task) => Boolean(task.runtime.query_text)).length,
      totalCost,
      todayCost,
      dbExists: overview.availability.runtime !== "offline",
      recentTasks: tasks.map((task) => task.runtime).slice(0, 8),
      dailyCosts: Array.from(dailyCostMap.entries())
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([date, cost]) => ({ date, cost })),
    };
  } catch {
    return buildEmptyBotStats(botId);
  }
}

export async function getOperationalBotStatsList() {
  const bots = await getControlPlaneBots();
  const stats = await Promise.all(bots.map(async (bot) => getOperationalBotStats(bot.id)));
  return bots.map((bot) => stats.find((item) => item.botId === bot.id) ?? buildEmptyBotStats(bot.id));
}

export async function getOperationalBotTasks(
  botId: string,
  options: { search?: string | null; status?: string | null; limit?: number | null } = {},
) {
  const { rows, snapshots } = await getBotRuntimeCollection(botId, options);
  return rows
    .map((row) => {
      const snapshot = snapshots.get(row.taskId);
      if (!snapshot?.task) return null;
      return toRuntimeTask(row, snapshot.task);
    })
    .filter((item): item is Task => Boolean(item))
    .sort((left, right) => toTimestamp(right.created_at) - toTimestamp(left.created_at));
}

export async function getOperationalExecutions(
  botId: string,
  options: { search?: string | null; status?: string | null; limit?: number | null } = {},
) {
  const { rows, snapshots } = await getBotRuntimeCollection(botId, options);
  return rows
    .map((row) => {
      const snapshot = snapshots.get(row.taskId);
      if (!snapshot?.task) return null;
      return toExecutionSummary(botId, row, snapshot.task, snapshot.warnings ?? []);
    })
    .filter((item): item is ExecutionSummary => Boolean(item))
    .sort((left, right) => toTimestamp(right.created_at) - toTimestamp(left.created_at));
}

function mapRuntimeEvent(event: RuntimeEvent, index: number) {
  const severity = String(event.severity || "info").toLowerCase();
  const status: ExecutionDetail["timeline"][number]["status"] =
    severity === "error"
      ? "error"
      : severity === "warning"
        ? "warning"
        : event.type?.toLowerCase().includes("complete")
          ? "success"
          : "info";
  const payload =
    event.payload && typeof event.payload === "object" && !Array.isArray(event.payload)
      ? (event.payload as Record<string, unknown>)
      : {};
  const summary =
    typeof payload.message === "string"
      ? payload.message
      : typeof event.type === "string"
        ? event.type
        : `event-${index + 1}`;

  return {
    id: `${event.seq ?? index}-${event.type ?? "event"}`,
    type: String(event.type || "event"),
    title: String(event.type || "event"),
    summary,
    status,
    timestamp: typeof event.ts === "string" ? event.ts : null,
    details: payload,
  };
}

function mapRuntimeArtifacts(bundle: RuntimeTaskBundle): ExecutionArtifact[] {
  const artifacts: ExecutionArtifact[] = bundle.artifacts.map((artifact, index) => ({
    id: `artifact-${artifact.id ?? index}`,
    label: String(artifact.label || artifact.artifact_kind || `artifact-${index + 1}`),
    kind: "json",
    content: {
      artifact_kind: artifact.artifact_kind,
      path: artifact.path,
      metadata: artifact.metadata ?? {},
      created_at: artifact.created_at,
      expires_at: artifact.expires_at,
    },
  }));

  if (bundle.workspaceStatus?.text) {
    artifacts.push({
      id: "workspace-status",
      label: "Workspace status",
      kind: "text",
      content: bundle.workspaceStatus.text,
    });
  }

  if (bundle.workspaceDiff?.text) {
    artifacts.push({
      id: "workspace-diff",
      label: "Workspace diff",
      kind: "text",
      content: bundle.workspaceDiff.text,
    });
  }

  if (bundle.services.length > 0) {
    artifacts.push({
      id: "service-endpoints",
      label: "Service endpoints",
      kind: "json",
      content: bundle.services,
    });
  }

  if (bundle.resources.length > 0) {
    artifacts.push({
      id: "resource-samples",
      label: "Resource samples",
      kind: "json",
      content: bundle.resources,
    });
  }

  return artifacts;
}

function collectWarnings(warnings: RuntimeWarning[], guardrails: RuntimeGuardrailHit[]) {
  const warningMessages = warnings
    .map((warning) => (typeof warning.message === "string" ? warning.message : null))
    .filter((item): item is string => Boolean(item));
  const guardrailMessages = guardrails.map((guardrail) => {
    const type = typeof guardrail.guardrail_type === "string" ? guardrail.guardrail_type : "guardrail";
    return `${type}`;
  });
  return [...warningMessages, ...guardrailMessages];
}

export async function getOperationalExecutionDetail(
  botId: string,
  taskId: number,
) {
  const bundle = await getRuntimeTaskBundle(botId, taskId);
  if (!bundle.task) {
    throw new Error("Task not found");
  }

  const task = bundle.task;
  const timeline = bundle.events.map(mapRuntimeEvent);
  const warnings = collectWarnings(bundle.warnings, bundle.guardrails);

  return {
    task_id: Number(task.id ?? taskId),
    bot_id: botId,
    status: (String(task.status || "queued") as ExecutionSummary["status"]),
    query_text: typeof task.query_text === "string" ? task.query_text : null,
    response_text: null,
    model: typeof task.model === "string" ? task.model : null,
    session_id: typeof task.session_id === "string" ? task.session_id : null,
    work_dir: typeof task.work_dir === "string" ? task.work_dir : null,
    user_id: Number(task.user_id ?? 0),
    chat_id: Number(task.chat_id ?? 0),
    created_at: String(task.created_at || new Date().toISOString()),
    started_at: typeof task.started_at === "string" ? task.started_at : null,
    completed_at: typeof task.completed_at === "string" ? task.completed_at : null,
    cost_usd: Number(task.cost_usd ?? 0),
    duration_ms: computeDurationMs(task),
    attempt: Number(task.attempt ?? 1),
    max_attempts: Number(task.max_attempts ?? 1),
    error_message: typeof task.error_message === "string" ? task.error_message : null,
    stop_reason:
      typeof task.current_phase === "string"
        ? task.current_phase
        : typeof task.status === "string"
          ? task.status
          : null,
    warnings,
    has_rich_trace: false,
    trace_source: "missing",
    response_source: "missing",
    tools_source: "missing",
    tool_count: 0,
    timeline,
    tools: [],
    reasoning_summary: warnings,
    artifacts: mapRuntimeArtifacts(bundle),
    redactions: null,
  } satisfies ExecutionDetail;
}

export async function getOperationalSessions(
  botId: string,
  options: { search?: string | null; limit?: number | null } = {},
) {
  const executions = await getOperationalExecutions(botId, { search: options.search, limit: 200 });
  const sessionMap = new Map<string, SessionSummary>();

  for (const execution of executions) {
    const sessionId = execution.session_id || `runtime-task-${execution.task_id}`;
    const current = sessionMap.get(sessionId);
    const createdAt = execution.created_at;
    const lastActivityAt = execution.completed_at || execution.started_at || execution.created_at;

    if (!current) {
      sessionMap.set(sessionId, {
        bot_id: botId,
        session_id: sessionId,
        name: execution.query_text?.slice(0, 72) || `Runtime session #${execution.task_id}`,
        user_id: execution.user_id,
        created_at: createdAt,
        last_used: lastActivityAt,
        last_activity_at: lastActivityAt,
        query_count: execution.query_text ? 1 : 0,
        execution_count: 1,
        total_cost_usd: execution.cost_usd,
        running_count: ["queued", "running", "retrying"].includes(execution.status) ? 1 : 0,
        failed_count: execution.status === "failed" ? 1 : 0,
        latest_status: execution.status,
        latest_query_preview: execution.query_text,
        latest_response_preview: null,
        latest_message_preview: execution.query_text,
      });
      continue;
    }

    current.query_count += execution.query_text ? 1 : 0;
    current.execution_count += 1;
    current.total_cost_usd += execution.cost_usd;
    current.running_count += ["queued", "running", "retrying"].includes(execution.status) ? 1 : 0;
    current.failed_count += execution.status === "failed" ? 1 : 0;
    if (toTimestamp(createdAt) < toTimestamp(current.created_at)) {
      current.created_at = createdAt;
    }
    if (toTimestamp(lastActivityAt) >= toTimestamp(current.last_activity_at)) {
      current.last_used = lastActivityAt;
      current.last_activity_at = lastActivityAt;
      current.latest_status = execution.status;
      current.latest_query_preview = execution.query_text;
      current.latest_message_preview = execution.query_text;
    }
  }

  const items = Array.from(sessionMap.values()).sort(
    (left, right) => toTimestamp(right.last_activity_at) - toTimestamp(left.last_activity_at),
  );

  if (options.limit && options.limit > 0) {
    return items.slice(0, options.limit);
  }

  return items;
}

export async function getOperationalSessionDetail(botId: string, sessionId: string) {
  const executions = (await getOperationalExecutions(botId, { limit: 200 }))
    .filter((execution) => (execution.session_id || `runtime-task-${execution.task_id}`) === sessionId)
    .sort((left, right) => toTimestamp(left.created_at) - toTimestamp(right.created_at));

  if (executions.length === 0) {
    throw new Error("Session not found");
  }

  const summaryBase = executions[0];
  const summary: SessionSummary = {
    bot_id: botId,
    session_id: sessionId,
    name: summaryBase.query_text?.slice(0, 72) || `Runtime session #${summaryBase.task_id}`,
    user_id: summaryBase.user_id,
    created_at: executions[0]?.created_at ?? null,
    last_used: executions[executions.length - 1]?.completed_at || executions[executions.length - 1]?.started_at || executions[executions.length - 1]?.created_at || null,
    last_activity_at: executions[executions.length - 1]?.completed_at || executions[executions.length - 1]?.started_at || executions[executions.length - 1]?.created_at || null,
    query_count: executions.filter((execution) => Boolean(execution.query_text)).length,
    execution_count: executions.length,
    total_cost_usd: executions.reduce((sum, execution) => sum + execution.cost_usd, 0),
    running_count: executions.filter((execution) => ["queued", "running", "retrying"].includes(execution.status)).length,
    failed_count: executions.filter((execution) => execution.status === "failed").length,
    latest_status: executions[executions.length - 1]?.status ?? null,
    latest_query_preview: executions[executions.length - 1]?.query_text ?? null,
    latest_response_preview: null,
    latest_message_preview: executions[executions.length - 1]?.query_text ?? null,
  };

  const messages: SessionMessage[] = executions.flatMap((execution) => {
    const userMessage: SessionMessage = {
      id: `${execution.task_id}-user`,
      role: "user",
      text: execution.query_text || `Runtime task #${execution.task_id}`,
      timestamp: execution.created_at,
      model: execution.model,
      cost_usd: execution.cost_usd,
      query_id: execution.task_id,
      session_id: sessionId,
      error: false,
      linked_execution: execution,
    };
    const assistantMessage: SessionMessage = {
      id: `${execution.task_id}-assistant`,
      role: "assistant",
      text:
        execution.error_message ||
        `Execution ${execution.status} in runtime room #${execution.task_id}.`,
      timestamp: execution.completed_at || execution.started_at || execution.created_at,
      model: execution.model,
      cost_usd: execution.cost_usd,
      query_id: execution.task_id,
      session_id: sessionId,
      error: execution.status === "failed",
      linked_execution: execution,
    };
    return execution.query_text ? [userMessage, assistantMessage] : [assistantMessage];
  });

  return {
    summary,
    messages,
    orphan_executions: [],
    totals: {
      messages: messages.length,
      executions: executions.length,
      tools: executions.reduce((sum, execution) => sum + execution.tool_count, 0),
      cost_usd: summary.total_cost_usd,
    },
  } satisfies SessionDetail;
}

export async function getOperationalDlq(
  botId: string,
  options: { retryEligible?: boolean | null; limit?: number | null } = {},
) {
  const executions = await getOperationalExecutions(botId, { limit: options.limit ?? 100 });
  const items = executions
    .filter((execution) => execution.status === "failed")
    .map((execution) => ({
      id: execution.task_id,
      task_id: execution.task_id,
      user_id: execution.user_id,
      chat_id: execution.chat_id,
      bot_id: botId,
      pod_name: null,
      query_text: execution.query_text || `Runtime task #${execution.task_id}`,
      model: execution.model,
      error_message: execution.error_message,
      error_class: execution.stop_reason,
      attempt_count: execution.attempt,
      original_created_at: execution.created_at,
      failed_at: execution.completed_at || execution.started_at || execution.created_at,
      retry_eligible: execution.attempt < execution.max_attempts ? 1 : 0,
      retried_at: execution.status === "retrying" ? execution.started_at : null,
      metadata_json: JSON.stringify({
        trace_source: execution.trace_source,
        warning_count: execution.warning_count,
        status: execution.status,
      }),
    } satisfies DLQEntry))
    .filter((entry) =>
      options.retryEligible == null
        ? true
        : options.retryEligible
          ? entry.retry_eligible === 1
          : entry.retry_eligible === 0,
    );

  return items;
}

function classifyTaskType(queryText: string | null, model: string | null) {
  const haystack = [queryText, model].filter(Boolean).join(" ").toLowerCase();
  if (/(jira|ticket|issue|backlog|sprint)/.test(haystack)) return { value: "jira_update", label: "Jira" };
  if (/(summary|resumo|tl;dr|recap)/.test(haystack)) return { value: "summarization", label: "Resumo" };
  if (/(search|research|pesquisa|investiga)/.test(haystack)) return { value: "research", label: "Pesquisa" };
  return { value: "runtime_execution", label: "Execucao" };
}

export async function getOperationalCostInsights(filters: {
  botIds?: string[];
  period?: string | null;
  model?: string | null;
  taskType?: string | null;
}) {
  const bots = await getControlPlaneBots();
  const selectedBotIds = (filters.botIds && filters.botIds.length > 0
    ? filters.botIds
    : bots.map((bot) => bot.id)
  ).filter(Boolean);

  const executionLists = await Promise.all(
    selectedBotIds.map(async (botId) => getOperationalExecutions(botId, { limit: 200 })),
  );
  const executions = executionLists
    .flat()
    .filter((execution) =>
      filters.model ? execution.model === filters.model : true,
    );

  const taskTypeEntries = executions.map((execution) => ({
    execution,
    taskType: classifyTaskType(execution.query_text, execution.model),
  }));
  const filteredEntries = taskTypeEntries.filter((entry) =>
    filters.taskType ? entry.taskType.value === filters.taskType : true,
  );

  const overview: CostOverview = {
    total_cost_usd: filteredEntries.reduce((sum, entry) => sum + entry.execution.cost_usd, 0),
    today_cost_usd: filteredEntries
      .filter((entry) => toIsoDay(entry.execution.created_at) === new Date().toISOString().slice(0, 10))
      .reduce((sum, entry) => sum + entry.execution.cost_usd, 0),
    resolved_conversations: new Set(
      filteredEntries
        .filter((entry) => entry.execution.status === "completed")
        .map((entry) => entry.execution.session_id || `runtime-task-${entry.execution.task_id}`),
    ).size,
    unresolved_conversations: new Set(
      filteredEntries
        .filter((entry) => entry.execution.status !== "completed")
        .map((entry) => entry.execution.session_id || `runtime-task-${entry.execution.task_id}`),
    ).size,
    avg_cost_per_resolved_conversation: 0,
    median_cost_per_resolved_conversation: 0,
    unresolved_cost_usd: filteredEntries
      .filter((entry) => entry.execution.status !== "completed")
      .reduce((sum, entry) => sum + entry.execution.cost_usd, 0),
    total_queries: filteredEntries.filter((entry) => Boolean(entry.execution.query_text)).length,
    total_executions: filteredEntries.length,
    top_model: null,
    top_bot: null,
    top_task_type: null,
  };

  const timeSeriesMap = new Map<string, CostTimePoint>();
  const botCostMap = new Map<string, number>();
  const modelCostMap = new Map<string, number>();
  const taskTypeCostMap = new Map<string, { label: string; cost: number; count: number }>();

  for (const entry of filteredEntries) {
    const bucket = toIsoDay(entry.execution.created_at) || "unknown";
    const existingPoint = timeSeriesMap.get(bucket) ?? {
      bucket,
      label: bucket,
      total_cost_usd: 0,
      by_bot: {},
      by_model: {},
    };
    existingPoint.total_cost_usd += entry.execution.cost_usd;
    existingPoint.by_bot[entry.execution.bot_id] =
      (existingPoint.by_bot[entry.execution.bot_id] ?? 0) + entry.execution.cost_usd;
    if (entry.execution.model) {
      existingPoint.by_model[entry.execution.model] =
        (existingPoint.by_model[entry.execution.model] ?? 0) + entry.execution.cost_usd;
      modelCostMap.set(
        entry.execution.model,
        (modelCostMap.get(entry.execution.model) ?? 0) + entry.execution.cost_usd,
      );
    }
    timeSeriesMap.set(bucket, existingPoint);
    botCostMap.set(
      entry.execution.bot_id,
      (botCostMap.get(entry.execution.bot_id) ?? 0) + entry.execution.cost_usd,
    );
    const taskTypeEntry = taskTypeCostMap.get(entry.taskType.value) ?? {
      label: entry.taskType.label,
      cost: 0,
      count: 0,
    };
    taskTypeEntry.cost += entry.execution.cost_usd;
    taskTypeEntry.count += 1;
    taskTypeCostMap.set(entry.taskType.value, taskTypeEntry);
  }

  const totalCost = overview.total_cost_usd || 1;
  const byBot = Array.from(botCostMap.entries()).map(([botId, cost]) => ({
    bot_id: botId,
    cost_usd: cost,
    share_pct: (cost / totalCost) * 100,
    resolved_conversations: 0,
    avg_cost_per_resolved_conversation: 0,
    query_count: filteredEntries.filter((entry) => entry.execution.bot_id === botId && Boolean(entry.execution.query_text)).length,
    execution_count: filteredEntries.filter((entry) => entry.execution.bot_id === botId).length,
  }));
  const byModel = Array.from(modelCostMap.entries()).map(([model, cost]) => ({
    model,
    cost_usd: cost,
    share_pct: (cost / totalCost) * 100,
    query_count: filteredEntries.filter((entry) => entry.execution.model === model && Boolean(entry.execution.query_text)).length,
    execution_count: filteredEntries.filter((entry) => entry.execution.model === model).length,
    resolved_conversations: 0,
  }));
  const byTaskType = Array.from(taskTypeCostMap.entries()).map(([taskType, entry]) => ({
    task_type: taskType,
    label: entry.label,
    cost_usd: entry.cost,
    share_pct: (entry.cost / totalCost) * 100,
    avg_cost_usd: entry.count > 0 ? entry.cost / entry.count : 0,
    count: entry.count,
  }));

  overview.top_bot = byBot.sort((left, right) => right.cost_usd - left.cost_usd)[0]?.bot_id ?? null;
  overview.top_model = byModel.sort((left, right) => right.cost_usd - left.cost_usd)[0]?.model ?? null;
  overview.top_task_type =
    byTaskType.sort((left, right) => right.cost_usd - left.cost_usd)[0]?.task_type ?? null;

  const peakBucket = Array.from(timeSeriesMap.values()).sort(
    (left, right) => right.total_cost_usd - left.total_cost_usd,
  )[0];
  const peak: CostPeakBucket | null = peakBucket
    ? {
        bucket: peakBucket.bucket,
        label: peakBucket.label,
        cost_usd: peakBucket.total_cost_usd,
        top_bot:
          Object.entries(peakBucket.by_bot).sort((left, right) => right[1] - left[1])[0]?.[0] ?? null,
        top_model:
          Object.entries(peakBucket.by_model).sort((left, right) => right[1] - left[1])[0]?.[0] ?? null,
        top_task_type: overview.top_task_type,
      }
    : null;

  const conversationRows: CostConversationRow[] = Array.from(
    filteredEntries.reduce((acc, entry) => {
      const sessionId = entry.execution.session_id || `runtime-task-${entry.execution.task_id}`;
      const normalizedStatus: CostConversationRow["status"] =
        entry.execution.status === "completed"
          ? "resolved"
          : entry.execution.status === "retrying"
            ? "running"
            : entry.execution.status === "failed"
              ? "failed"
              : entry.execution.status === "queued"
                ? "queued"
                : "running";
      const current: CostConversationRow = acc.get(sessionId) ?? {
        bot_id: entry.execution.bot_id,
        session_id: sessionId,
        name: entry.execution.query_text?.slice(0, 72) || sessionId,
        status: normalizedStatus,
        cost_usd: 0,
        query_count: 0,
        execution_count: 0,
        resolved: false,
        dominant_model: entry.execution.model,
        task_type_mix: [],
        latest_message_preview: entry.execution.query_text,
        last_activity_at: entry.execution.completed_at || entry.execution.started_at || entry.execution.created_at,
        created_at: entry.execution.created_at,
        resolved_at: entry.execution.completed_at,
      };
      current.cost_usd += entry.execution.cost_usd;
      current.query_count += entry.execution.query_text ? 1 : 0;
      current.execution_count += 1;
      current.resolved = current.resolved || entry.execution.status === "completed";
      if (!current.task_type_mix.includes(entry.taskType.label)) {
        current.task_type_mix.push(entry.taskType.label);
      }
      acc.set(sessionId, current);
      return acc;
    }, new Map<string, CostConversationRow>()).values(),
  );

  const comparison: CostComparison = {
    previous_total_cost_usd: 0,
    total_delta_pct: null,
    previous_avg_cost_per_resolved_conversation: 0,
    avg_cost_per_resolved_delta_pct: null,
    previous_today_cost_usd: null,
    today_delta_pct: null,
    previous_resolved_conversations: 0,
  };

  return {
    overview,
    comparison,
    peak_bucket: peak,
    time_series: Array.from(timeSeriesMap.values()).sort((left, right) => left.bucket.localeCompare(right.bucket)),
    by_bot: byBot,
    by_model: byModel,
    by_task_type: byTaskType,
    resolved_conversations: conversationRows
      .filter((row) => row.resolved)
      .map((row) => ({
        bot_id: row.bot_id,
        session_id: row.session_id,
        name: row.name,
        cost_usd: row.cost_usd,
        query_count: row.query_count,
        execution_count: row.execution_count,
        resolved_at: row.resolved_at,
        dominant_model: row.dominant_model,
        latest_message_preview: row.latest_message_preview,
      })),
    conversation_rows: conversationRows,
    available_models: Array.from(
      new Set(filteredEntries.map((entry) => entry.execution.model).filter((value): value is string => Boolean(value))),
    ),
    available_task_types: byTaskType.map((entry) => ({ value: entry.task_type, label: entry.label })),
    applied_filters: {
      bot_id: selectedBotIds.length === 1 ? selectedBotIds[0] : "all",
      bot_ids: selectedBotIds,
      period: filters.period || "runtime",
      from: null,
      to: null,
      model: filters.model || null,
      task_type: filters.taskType || null,
      group_by: "day",
    },
  } satisfies CostInsightsResponse;
}

export async function getOperationalSchedulerSurface() {
  const settings = await getControlPlaneSystemSettings();
  return {
    scheduler: settings.scheduler ?? {},
    runtime: settings.runtime ?? {},
    knowledge: settings.knowledge ?? {},
  };
}

export function getUnavailableCronJobs(): CronJob[] {
  return [];
}
