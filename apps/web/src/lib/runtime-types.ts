export type RuntimeAvailabilityStatus =
  | "available"
  | "partial"
  | "unavailable"
  | "disabled"
  | "offline"
  | "unknown";

export interface RuntimeAvailability {
  health: RuntimeAvailabilityStatus;
  database: RuntimeAvailabilityStatus;
  runtime: RuntimeAvailabilityStatus;
  browser: RuntimeAvailabilityStatus;
  attach: RuntimeAvailabilityStatus;
  errors: string[];
}

export interface RuntimeHealthSnapshot {
  root_dir?: string;
  heartbeat_interval_seconds?: number;
  resource_sample_interval_seconds?: number;
  active_environments?: number;
  retained_environments?: number;
  stale_environments?: number;
  environments_by_phase?: Record<string, number>;
  queues?: RuntimeQueueItem[];
  browser_sessions_active?: number;
  attach_sessions_terminal?: number;
  attach_sessions_browser?: number;
  cleanup_backlog?: number;
  recovery_backlog?: number;
  service_endpoints?: number;
  disk?: {
    total_bytes?: number;
    used_bytes?: number;
    free_bytes?: number;
  };
  error?: string;
  [key: string]: unknown;
}

export interface RuntimeBotHealth {
  status?: string;
  active_tasks?: number;
  active_processes?: number;
  database?: {
    reachable?: boolean;
    ready?: boolean;
    [key: string]: unknown;
  };
  runtime?: RuntimeHealthSnapshot | null;
  [key: string]: unknown;
}

export interface RuntimeReadinessBackgroundLoops {
  started?: boolean;
  ready?: boolean;
  critical_ready?: boolean;
  degraded_loops?: string[];
  loops?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RuntimeReadinessKnowledgeHealth {
  ready?: boolean;
  storage_mode?: string;
  primary_backend?: {
    enabled?: boolean;
    ready?: boolean;
    pool_active?: boolean;
    [key: string]: unknown;
  };
  object_store?: {
    enabled?: boolean;
    ready?: boolean;
    [key: string]: unknown;
  };
  ingest_worker?: {
    enabled?: boolean;
    ready?: boolean;
    queue?: {
      enabled?: boolean;
      ready?: boolean;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface RuntimeReadiness {
  ready?: boolean;
  reasons?: string[];
  startup?: {
    phase?: string;
    details?: Record<string, unknown>;
    expected_background_loops?: string[];
    [key: string]: unknown;
  };
  background_loops?: RuntimeReadinessBackgroundLoops;
  knowledge_v2?: RuntimeReadinessKnowledgeHealth;
  supervision?: {
    ready?: boolean;
    degraded_loops?: string[];
    loops?: Record<string, unknown>;
    [key: string]: unknown;
  };
  browser_live?: {
    ready?: boolean;
    enabled?: boolean;
    [key: string]: unknown;
  };
  runtime_root?: {
    ready?: boolean;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface RuntimeQueueItem {
  task_id: number;
  user_id?: number | null;
  chat_id?: number | null;
  queue_name?: string | null;
  status?: string | null;
  queue_position?: number | null;
  query_text?: string | null;
  queued_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeEnvironment {
  id: number;
  task_id: number;
  user_id?: number | null;
  chat_id?: number | null;
  classification?: string | null;
  environment_kind?: string | null;
  isolation?: string | null;
  duration?: string | null;
  status?: string | null;
  current_phase?: string | null;
  workspace_path?: string | null;
  runtime_dir?: string | null;
  base_work_dir?: string | null;
  branch_name?: string | null;
  created_worktree?: number | boolean | null;
  worktree_mode?: string | null;
  is_pinned?: number | boolean | null;
  checkpoint_status?: string | null;
  checkpoint_path?: string | null;
  parent_env_id?: number | null;
  lineage_root_env_id?: number | null;
  source_checkpoint_id?: number | null;
  recovery_state?: string | null;
  revision?: number | null;
  browser_transport?: string | null;
  display_id?: number | null;
  vnc_port?: number | null;
  novnc_port?: number | null;
  pause_state?: string | null;
  pause_reason?: string | null;
  save_verified_at?: string | null;
  process_pid?: number | null;
  process_pgid?: number | null;
  browser_scope_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_heartbeat_at?: string | null;
  retention_expires_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeTaskDetail {
  id: number;
  user_id?: number | null;
  chat_id?: number | null;
  status?: string | null;
  query_text?: string | null;
  provider?: string | null;
  model?: string | null;
  work_dir?: string | null;
  attempt?: number | null;
  max_attempts?: number | null;
  cost_usd?: number | null;
  error_message?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  session_id?: string | null;
  provider_session_id?: string | null;
  source_task_id?: number | null;
  source_action?: string | null;
  env_id?: number | null;
  classification?: string | null;
  environment_kind?: string | null;
  current_phase?: string | null;
  last_heartbeat_at?: string | null;
  retention_expires_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeWarning {
  id: number;
  task_id: number;
  env_id?: number | null;
  warning_type?: string | null;
  message?: string | null;
  details?: Record<string, unknown>;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeEvent {
  seq: number;
  task_id?: number | null;
  env_id?: number | null;
  attempt?: number | null;
  phase?: string | null;
  type?: string | null;
  severity?: string | null;
  payload?: Record<string, unknown>;
  artifact_refs?: string[];
  resource_snapshot_ref?: string | null;
  ts?: string | null;
  botId?: string;
  [key: string]: unknown;
}

export interface RuntimeArtifact {
  id: number;
  task_id: number;
  env_id?: number | null;
  artifact_kind?: string | null;
  label?: string | null;
  path?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  expires_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeCheckpoint {
  id: number;
  task_id: number;
  env_id?: number | null;
  status?: string | null;
  checkpoint_dir?: string | null;
  manifest_path?: string | null;
  patch_path?: string | null;
  commit_sha?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  expires_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeTerminal {
  id: number;
  task_id: number;
  env_id?: number | null;
  terminal_kind?: string | null;
  label?: string | null;
  path?: string | null;
  stream_path?: string | null;
  interactive?: number | boolean | null;
  cursor_offset?: number | null;
  last_offset?: number | null;
  preview?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeBrowserSession {
  id: number;
  task_id: number;
  env_id?: number | null;
  scope_id?: number | null;
  transport?: string | null;
  status?: string | null;
  display_id?: number | null;
  vnc_port?: number | null;
  novnc_port?: number | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
  ended_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeBrowserState {
  scope_id?: number | null;
  transport?: string | null;
  status?: string | null;
  display_id?: number | null;
  vnc_port?: number | null;
  novnc_port?: number | null;
  runtime_dir?: string | null;
  missing_binaries?: string[];
  xvfb_pid?: number | null;
  openbox_pid?: number | null;
  x11vnc_pid?: number | null;
  websockify_pid?: number | null;
  novnc_url?: string | null;
  visual_available?: boolean;
  session_persisted_only?: boolean;
  unavailable_reason?: string | null;
  last_known_status?: string | null;
  [key: string]: unknown;
}

export interface RuntimeWorkspaceTreeEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number | null;
}

export interface RuntimeWorkspaceFile {
  path: string;
  content: string;
  truncated?: boolean;
}

export interface RuntimeWorkspaceStatus {
  ok?: boolean;
  text?: string;
  [key: string]: unknown;
}

export interface RuntimeWorkspaceDiff {
  ok?: boolean;
  text?: string;
  truncated?: boolean;
  [key: string]: unknown;
}

export interface RuntimeServiceEndpoint {
  id: number;
  task_id: number;
  env_id?: number | null;
  process_id?: number | null;
  service_kind?: string | null;
  label?: string | null;
  host?: string | null;
  port?: number | null;
  protocol?: string | null;
  status?: string | null;
  url?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
  ended_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeResourceSample {
  id: number;
  task_id: number;
  env_id?: number | null;
  cpu_percent?: number | null;
  rss_kb?: number | null;
  process_count?: number | null;
  workspace_disk_bytes?: number | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeLoopCycle {
  id: number;
  task_id: number;
  env_id?: number | null;
  cycle_index?: number | null;
  phase?: string | null;
  goal?: string | null;
  plan?: Record<string, unknown>;
  hypothesis?: string | null;
  command_fingerprint?: string | null;
  diff_hash?: string | null;
  failure_fingerprint?: string | null;
  validations?: Array<Record<string, unknown>>;
  outcome?: Record<string, unknown>;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeGuardrailHit {
  id: number;
  task_id: number;
  env_id?: number | null;
  cycle_id?: number | null;
  guardrail_type?: string | null;
  details?: Record<string, unknown>;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeAttachSession {
  id?: number;
  task_id: number;
  env_id?: number | null;
  attach_kind?: string | null;
  terminal_id?: number | null;
  token?: string | null;
  can_write?: number | boolean | null;
  actor?: string | null;
  status?: string | null;
  expires_at?: string | null;
  created_at?: string | null;
  last_seen_at?: string | null;
  ended_at?: string | null;
  [key: string]: unknown;
}

export interface RuntimeSessions {
  attach_sessions: RuntimeAttachSession[];
  browser_sessions: RuntimeBrowserSession[];
  terminals: RuntimeTerminal[];
  [key: string]: unknown;
}

export interface RuntimeMutationResult {
  ok?: boolean;
  error?: string;
  action?: string;
  task_id?: number;
  env_id?: number | null;
  final_phase?: string | null;
  pinned?: boolean;
  force?: boolean;
  environment?: RuntimeEnvironment;
  [key: string]: unknown;
}

export interface RuntimeOverview {
  botId: string;
  botLabel: string;
  botColor: string;
  baseUrl: string;
  fetchedAt: string;
  health: RuntimeBotHealth | null;
  snapshot: RuntimeHealthSnapshot | null;
  readiness?: RuntimeReadiness | null;
  availability: RuntimeAvailability;
  queues: RuntimeQueueItem[];
  environments: RuntimeEnvironment[];
  incidents: string[];
  activeTaskIds: number[];
  retainedTaskIds: number[];
}

export interface RuntimeTaskBundle {
  botId: string;
  fetchedAt: string;
  availability: RuntimeAvailability;
  task: RuntimeTaskDetail | null;
  environment: RuntimeEnvironment | null;
  warnings: RuntimeWarning[];
  guardrails: RuntimeGuardrailHit[];
  events: RuntimeEvent[];
  artifacts: RuntimeArtifact[];
  checkpoints: RuntimeCheckpoint[];
  terminals: RuntimeTerminal[];
  browser: RuntimeBrowserState;
  browserSessions: RuntimeBrowserSession[];
  workspaceTree: RuntimeWorkspaceTreeEntry[];
  workspaceStatus: RuntimeWorkspaceStatus;
  workspaceDiff: RuntimeWorkspaceDiff;
  services: RuntimeServiceEndpoint[];
  resources: RuntimeResourceSample[];
  loopCycles: RuntimeLoopCycle[];
  sessions: RuntimeSessions;
  errors: string[];
}
