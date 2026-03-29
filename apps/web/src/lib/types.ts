// Mirrors SQLite table schemas from database.py

export interface Task {
  id: number;
  user_id: number;
  chat_id: number;
  status: "queued" | "running" | "completed" | "failed" | "retrying";
  query_text: string | null;
  model: string | null;
  work_dir: string | null;
  attempt: number;
  max_attempts: number;
  cost_usd: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  session_id: string | null;
}

export interface Query {
  id: number;
  user_id: number | null;
  timestamp: string | null;
  query_text: string | null;
  response_text: string | null;
  cost_usd: number | null;
  model: string | null;
  session_id: string | null;
  work_dir: string | null;
  error: number;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  event_type: string;
  bot_id: string | null;
  pod_name: string | null;
  user_id: number | null;
  task_id: number | null;
  trace_id: string | null;
  details_json: string;
  details: Record<string, unknown>;
  cost_usd: number | null;
  duration_ms: number | null;
}

export interface ExecutionRedactionSummary {
  count: number;
  fields: string[];
}

export interface ExecutionTimelineItem {
  id: string;
  type: string;
  title: string;
  summary: string | null;
  status: "info" | "success" | "warning" | "error";
  timestamp: string | null;
  details: Record<string, unknown>;
}

export interface ExecutionToolTrace {
  id: string;
  tool: string;
  category: string;
  success: boolean | null;
  duration_ms: number | null;
  started_at: string | null;
  completed_at: string | null;
  params: Record<string, unknown>;
  output: string | null;
  metadata: Record<string, unknown>;
  summary: string;
  redactions: ExecutionRedactionSummary | null;
}

export interface ExecutionArtifact {
  id: string;
  label: string;
  kind: "text" | "json" | "code";
  content: string | Record<string, unknown> | unknown[];
  description?: string;
  language?: string;
  unavailable?: boolean;
}

export interface ExecutionSummary {
  task_id: number;
  bot_id: string;
  status: Task["status"];
  query_text: string | null;
  model: string | null;
  session_id: string | null;
  user_id: number;
  chat_id: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  cost_usd: number;
  duration_ms: number | null;
  attempt: number;
  max_attempts: number;
  has_rich_trace: boolean;
  trace_source: "trace" | "legacy" | "missing";
  tool_count: number;
  warning_count: number;
  stop_reason: string | null;
  error_message: string | null;
  feedback_status?: string | null;
  retrieval_trace_id?: number | null;
  retrieval_strategy?: string | null;
  grounding_score?: number | null;
  citation_coverage?: number | null;
  answer_citation_coverage?: number | null;
  answer_gate_status?: string | null;
  answer_gate_reasons?: string[];
  post_write_review_required?: boolean;
  stale_sources_present?: boolean;
  ungrounded_operationally?: boolean;
  source_ref_count?: number;
  winning_source_count?: number;
  provenance_source?: "trace" | "episode" | "legacy" | "missing";
}

export interface ExecutionDetail {
  task_id: number;
  bot_id: string;
  status: Task["status"];
  query_text: string | null;
  response_text: string | null;
  model: string | null;
  session_id: string | null;
  work_dir: string | null;
  user_id: number;
  chat_id: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  cost_usd: number;
  duration_ms: number | null;
  attempt: number;
  max_attempts: number;
  error_message: string | null;
  stop_reason: string | null;
  warnings: string[];
  has_rich_trace: boolean;
  trace_source: "trace" | "legacy" | "missing";
  response_source: "trace" | "queries" | "missing";
  tools_source: "trace" | "audit" | "missing";
  tool_count: number;
  timeline: ExecutionTimelineItem[];
  tools: ExecutionToolTrace[];
  reasoning_summary: string[];
  artifacts: ExecutionArtifact[];
  redactions: ExecutionRedactionSummary | null;
  feedback_status?: string | null;
  retrieval_trace_id?: number | null;
  retrieval_strategy?: string | null;
  grounding_score?: number | null;
  citation_coverage?: number | null;
  answer_citation_coverage?: number | null;
  answer_gate_status?: string | null;
  answer_gate_reasons?: string[];
  post_write_review_required?: boolean;
  stale_sources_present?: boolean;
  ungrounded_operationally?: boolean;
  source_ref_count?: number;
  winning_source_count?: number;
  provenance_source?: "trace" | "episode" | "legacy" | "missing";
}

export interface CronJob {
  id: number;
  user_id: number | null;
  chat_id: number | null;
  cron_expression: string;
  command: string;
  description: string;
  created_at: string | null;
  enabled: number;
  work_dir: string | null;
}

export interface DLQEntry {
  id: number;
  task_id: number;
  user_id: number;
  chat_id: number;
  bot_id: string | null;
  pod_name: string | null;
  query_text: string;
  model: string | null;
  error_message: string | null;
  error_class: string | null;
  attempt_count: number;
  original_created_at: string | null;
  failed_at: string;
  retry_eligible: number;
  retried_at: string | null;
  metadata_json: string;
}

export interface Session {
  id: number;
  user_id: number | null;
  session_id: string;
  name: string | null;
  created_at: string | null;
  last_used: string | null;
}

export interface SessionSummary {
  bot_id: string;
  session_id: string;
  name: string | null;
  user_id: number | null;
  created_at: string | null;
  last_used: string | null;
  last_activity_at: string | null;
  query_count: number;
  execution_count: number;
  total_cost_usd: number;
  running_count: number;
  failed_count: number;
  latest_status: ExecutionSummary["status"] | null;
  latest_query_preview: string | null;
  latest_response_preview: string | null;
  latest_message_preview: string | null;
}

export interface SessionMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  timestamp: string | null;
  model: string | null;
  cost_usd: number | null;
  query_id: number;
  session_id: string;
  error: boolean;
  linked_execution?: ExecutionSummary | null;
}

export interface SessionDetail {
  summary: SessionSummary;
  messages: SessionMessage[];
  orphan_executions: ExecutionSummary[];
  totals: {
    messages: number;
    executions: number;
    tools: number;
    cost_usd: number;
  };
}

export interface SessionSendRequest {
  text: string;
  session_id?: string | null;
}

export interface SessionSendResponse {
  accepted: boolean;
  session_id: string;
  task_id?: number | null;
}

export type CostGroupBy = "auto" | "hour" | "day" | "week";

export interface CostOverview {
  total_cost_usd: number;
  today_cost_usd: number;
  resolved_conversations: number;
  unresolved_conversations: number;
  avg_cost_per_resolved_conversation: number;
  median_cost_per_resolved_conversation: number;
  unresolved_cost_usd: number;
  total_queries: number;
  total_executions: number;
  top_model: string | null;
  top_bot: string | null;
  top_task_type: string | null;
}

export interface CostTimePoint {
  bucket: string;
  label: string;
  total_cost_usd: number;
  by_bot: Record<string, number>;
  by_model: Record<string, number>;
}

export interface CostByBotItem {
  bot_id: string;
  cost_usd: number;
  share_pct: number;
  resolved_conversations: number;
  avg_cost_per_resolved_conversation: number;
  query_count: number;
  execution_count: number;
}

export interface CostByModelItem {
  model: string;
  cost_usd: number;
  share_pct: number;
  query_count: number;
  execution_count: number;
  resolved_conversations: number;
}

export interface CostByTaskTypeItem {
  task_type: string;
  label: string;
  cost_usd: number;
  share_pct: number;
  avg_cost_usd: number;
  count: number;
}

export interface ResolvedConversationCostItem {
  bot_id: string;
  session_id: string;
  name: string | null;
  cost_usd: number;
  query_count: number;
  execution_count: number;
  resolved_at: string | null;
  dominant_model: string | null;
  latest_message_preview: string | null;
}

export interface CostConversationRow {
  bot_id: string;
  session_id: string;
  name: string | null;
  status: "resolved" | "running" | "failed" | "queued" | "open";
  cost_usd: number;
  query_count: number;
  execution_count: number;
  resolved: boolean;
  dominant_model: string | null;
  task_type_mix: string[];
  latest_message_preview: string | null;
  last_activity_at: string | null;
  created_at: string | null;
  resolved_at: string | null;
}

export interface CostFiltersApplied {
  bot_id: string | "all";
  bot_ids: string[];
  period: string;
  from: string | null;
  to: string | null;
  model: string | null;
  task_type: string | null;
  group_by: CostGroupBy;
}

export interface CostComparison {
  previous_total_cost_usd: number;
  total_delta_pct: number | null;
  previous_avg_cost_per_resolved_conversation: number;
  avg_cost_per_resolved_delta_pct: number | null;
  previous_today_cost_usd: number | null;
  today_delta_pct: number | null;
  previous_resolved_conversations: number;
}

export interface CostPeakBucket {
  bucket: string;
  label: string;
  cost_usd: number;
  top_bot: string | null;
  top_model: string | null;
  top_task_type: string | null;
}

export interface CostInsightsResponse {
  overview: CostOverview;
  comparison: CostComparison;
  peak_bucket: CostPeakBucket | null;
  time_series: CostTimePoint[];
  by_bot: CostByBotItem[];
  by_model: CostByModelItem[];
  by_task_type: CostByTaskTypeItem[];
  resolved_conversations: ResolvedConversationCostItem[];
  conversation_rows: CostConversationRow[];
  available_models: string[];
  available_task_types: Array<{ value: string; label: string }>;
  applied_filters: CostFiltersApplied;
}

export type MemoryTypeKey =
  | "fact"
  | "procedure"
  | "event"
  | "preference"
  | "decision"
  | "problem"
  | "commit"
  | "relationship"
  | "task";

export type MemorySemanticStatus = "available" | "fallback" | "missing";

export interface MemoryMapUserOption {
  user_id: number;
  label: string;
  count: number;
}

export interface MemoryMapSessionOption {
  session_id: string;
  label: string;
  count: number;
  last_used: string | null;
}

export interface MemoryMapTypeOption {
  value: MemoryTypeKey;
  label: string;
  count: number;
  color: string;
}

export interface MemoryMapFilters {
  applied: {
    user_id: number | null;
    session_id: string | null;
    days: number;
    include_inactive: boolean;
    limit: number;
  };
  users: MemoryMapUserOption[];
  sessions: MemoryMapSessionOption[];
  types: MemoryMapTypeOption[];
}

interface MemoryMapNodeBase {
  id: string;
  kind: "memory" | "learning";
  bot_id: string;
  label: string;
  title: string;
  size: number;
  cluster_id: string | null;
  created_at: string | null;
  related_count: number;
}

export interface MemoryGraphNode extends MemoryMapNodeBase {
  kind: "memory";
  memory_id: number;
  memory_type: MemoryTypeKey;
  importance: number;
  access_count: number;
  is_active: boolean;
  session_id: string | null;
  user_id: number;
  last_accessed: string | null;
  expires_at: string | null;
  source_query_id: number | null;
  source_query_text: string | null;
  source_query_preview: string | null;
  content: string;
  metadata: Record<string, unknown>;
}

export interface MemoryLearningNode extends MemoryMapNodeBase {
  kind: "learning";
  dominant_type: MemoryTypeKey;
  importance: number;
  summary: string;
  member_ids: string[];
  member_count: number;
  session_ids: string[];
  semantic_strength: number | null;
}

export interface MemoryGraphEdge {
  id: string;
  source: string;
  target: string;
  type: "semantic" | "session" | "source" | "learning";
  weight: number;
  label: string;
  similarity: number | null;
  session_id: string | null;
  source_key: string | null;
}

export interface MemoryMapStats {
  total_memories: number;
  rendered_memories: number;
  hidden_memories: number;
  active_memories: number;
  inactive_memories: number;
  learning_nodes: number;
  users: number;
  sessions: number;
  semantic_edges: number;
  contextual_edges: number;
  expiring_soon: number;
  maintenance_operations: number;
  last_maintenance_at: string | null;
  semantic_status: MemorySemanticStatus;
}

export interface MemoryMapResponse {
  bot_id: string;
  stats: MemoryMapStats;
  filters: MemoryMapFilters;
  nodes: Array<MemoryGraphNode | MemoryLearningNode>;
  edges: MemoryGraphEdge[];
  semantic_status: MemorySemanticStatus;
}

export interface MemoryCurationPage {
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
}

export type MemoryReviewStatus =
  | "pending"
  | "approved"
  | "merged"
  | "discarded"
  | "expired"
  | "archived";

export type MemoryCurationTargetType = "memory" | "cluster";

export type MemoryCurationAction =
  | "approve"
  | "merge"
  | "discard"
  | "expire"
  | "archive"
  | "restore";

export interface MemoryReviewHistoryEntry {
  id: number;
  target_type: MemoryCurationTargetType;
  target_id: string;
  action: MemoryCurationAction;
  reason: string | null;
  duplicate_of_memory_id: number | null;
  created_at: string;
}

export interface MemoryReviewItem {
  bot_id: string;
  memory_id: number;
  memory_type: MemoryTypeKey;
  title: string;
  content: string;
  source_query_id: number | null;
  source_query_preview: string | null;
  session_id: string | null;
  user_id: number | null;
  importance: number;
  access_count: number;
  created_at: string | null;
  last_accessed: string | null;
  expires_at: string | null;
  review_status: MemoryReviewStatus;
  review_reason: string | null;
  duplicate_of_memory_id: number | null;
  cluster_id: string | null;
  semantic_strength: number | null;
  metadata: Record<string, unknown>;
  is_active: boolean;
}

export interface MemoryClusterReviewItem {
  cluster_id: string;
  bot_id: string;
  dominant_type: MemoryTypeKey;
  summary: string;
  member_count: number;
  member_ids: number[];
  session_ids: string[];
  semantic_strength: number | null;
  created_at: string | null;
  review_status: MemoryReviewStatus;
  review_reason: string | null;
}

export interface MemoryCurationOverview {
  pending_memories: number;
  pending_clusters: number;
  expiring_soon: number;
  discarded_last_7d: number;
  merged_last_7d: number;
  approved_last_7d: number;
}

export interface MemoryCurationAvailableFilters {
  statuses: Array<{ value: MemoryReviewStatus; label: string; count: number }>;
  types: Array<{ value: MemoryTypeKey; label: string; count: number; color: string }>;
}

export interface MemoryCurationResponse {
  bot_id: string;
  overview: MemoryCurationOverview;
  items: MemoryReviewItem[];
  clusters: MemoryClusterReviewItem[];
  available_filters: MemoryCurationAvailableFilters;
  page: MemoryCurationPage;
}

export interface MemoryReviewDetail {
  item: MemoryReviewItem;
  source_query_text: string | null;
  session_name: string | null;
  related_memories: MemoryReviewItem[];
  similar_memories: MemoryReviewItem[];
  cluster: MemoryClusterReviewItem | null;
  history: MemoryReviewHistoryEntry[];
}

export interface MemoryClusterReviewDetail {
  cluster: MemoryClusterReviewItem;
  members: MemoryReviewItem[];
  overlaps: Array<{ session_id: string; count: number }>;
  history: MemoryReviewHistoryEntry[];
}

export interface UserCost {
  user_id: number;
  total_cost: number;
  query_count: number;
  updated_at: string;
}

export interface BotStats {
  botId: string;
  totalTasks: number;
  activeTasks: number;
  completedTasks: number;
  failedTasks: number;
  queuedTasks: number;
  totalQueries: number;
  totalCost: number;
  todayCost: number;
  dbExists: boolean;
  recentTasks: Task[];
  dailyCosts: { date: string; cost: number }[];
}

export interface HealthStatus {
  status: string;
  uptime_seconds: number;
  active_processes: number;
  active_tasks: number;
  database: Record<string, unknown>;
  circuit_breakers: Record<string, unknown>;
  disk: Record<string, unknown>;
}
