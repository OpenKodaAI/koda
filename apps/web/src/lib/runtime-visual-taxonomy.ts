import {
  Activity,
  AlertTriangle,
  Archive,
  Ban,
  Bot,
  BrainCircuit,
  Braces,
  CalendarClock,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  Code2,
  CopyCheck,
  Database,
  FileArchive,
  FileCode2,
  FileOutput,
  FilePenLine,
  FileSearch,
  FileText,
  FlaskConical,
  GitBranch,
  Globe2,
  HardDrive,
  Hourglass,
  Image,
  KeyRound,
  ListChecks,
  LockKeyhole,
  MousePointerClick,
  PackageCheck,
  PlugZap,
  RefreshCcw,
  RotateCcw,
  Scissors,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Split,
  SquareTerminal,
  Trash2,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { RunGraphNodeType } from "@/lib/contracts/run-graph";
import type { SemanticTone } from "@/lib/theme-semantic";
import type { ExecutionArtifact, ExecutionSummary, ExecutionTimelineItem } from "@/lib/types";

export interface RuntimeVisualDescriptor {
  key: string;
  label: string;
  icon: LucideIcon;
  tone: SemanticTone;
}

export interface ToolVisualInput {
  tool?: string | null;
  category?: string | null;
  success?: boolean | null;
  metadata?: Record<string, unknown> | null;
}

const RUN_GRAPH_NODE_VISUALS: Record<RunGraphNodeType, RuntimeVisualDescriptor> = {
  queue_wait: { key: "queue_wait", label: "Queue wait", icon: Hourglass, tone: "warning" },
  lease_acquire: { key: "lease_acquire", label: "Lease acquired", icon: KeyRound, tone: "info" },
  lease_renew: { key: "lease_renew", label: "Lease renewed", icon: RefreshCcw, tone: "retry" },
  lease_lost: { key: "lease_lost", label: "Lease lost", icon: AlertTriangle, tone: "danger" },
  lease_reaped: { key: "lease_reaped", label: "Lease reaped", icon: Trash2, tone: "warning" },
  model_call: { key: "model_call", label: "Model call", icon: BrainCircuit, tone: "info" },
  tool_request: { key: "tool_request", label: "Tool request", icon: Send, tone: "warning" },
  tool_result: { key: "tool_result", label: "Tool result", icon: CheckCircle2, tone: "success" },
  tool_call: { key: "tool_call", label: "Tool call", icon: Wrench, tone: "info" },
  policy_gate: { key: "policy_gate", label: "Policy gate", icon: ShieldCheck, tone: "neutral" },
  approval_request: { key: "approval_request", label: "Approval request", icon: ShieldAlert, tone: "warning" },
  approval_decision: { key: "approval_decision", label: "Approval decision", icon: CopyCheck, tone: "success" },
  dependency_call: { key: "dependency_call", label: "Dependency call", icon: PlugZap, tone: "info" },
  breaker_open: { key: "breaker_open", label: "Breaker open", icon: ShieldAlert, tone: "danger" },
  retry_scheduled: { key: "retry_scheduled", label: "Retry scheduled", icon: RotateCcw, tone: "retry" },
  dlq_inserted: { key: "dlq_inserted", label: "DLQ inserted", icon: Archive, tone: "danger" },
  cancellation: { key: "cancellation", label: "Cancellation", icon: Ban, tone: "danger" },
  resource_cleanup: { key: "resource_cleanup", label: "Resource cleanup", icon: Scissors, tone: "neutral" },
  user_facing_error: { key: "user_facing_error", label: "User-facing error", icon: AlertTriangle, tone: "danger" },
  child_run: { key: "child_run", label: "Child run", icon: GitBranch, tone: "info" },
  squad_reply: { key: "squad_reply", label: "Squad reply", icon: Send, tone: "info" },
  agent_request: { key: "agent_request", label: "Agent request", icon: Bot, tone: "warning" },
  agent_followup: { key: "agent_followup", label: "Agent follow-up", icon: RefreshCcw, tone: "retry" },
  reply_obligation: { key: "reply_obligation", label: "Reply obligation", icon: ListChecks, tone: "warning" },
  coordinator_synthesis: { key: "coordinator_synthesis", label: "Coordinator synthesis", icon: Split, tone: "success" },
  artifact: { key: "artifact", label: "Artifact", icon: FileArchive, tone: "neutral" },
  cost: { key: "cost", label: "Cost", icon: CircleDollarSign, tone: "neutral" },
  context_block: { key: "context_block", label: "Context block", icon: Braces, tone: "info" },
  checkpoint: { key: "checkpoint", label: "Checkpoint", icon: CheckCircle2, tone: "success" },
  runtime_event: { key: "runtime_event", label: "Runtime event", icon: Activity, tone: "neutral" },
};

const EXECUTION_STATUS_VISUALS: Record<ExecutionSummary["status"], RuntimeVisualDescriptor> = {
  queued: { key: "queued", label: "Queued", icon: Hourglass, tone: "warning" },
  running: { key: "running", label: "Running", icon: Activity, tone: "info" },
  retrying: { key: "retrying", label: "Retrying", icon: RotateCcw, tone: "retry" },
  stalled: { key: "stalled", label: "Stalled", icon: AlertTriangle, tone: "warning" },
  degraded: { key: "degraded", label: "Degraded", icon: ShieldAlert, tone: "warning" },
  completed: { key: "completed", label: "Completed", icon: CheckCircle2, tone: "success" },
  failed: { key: "failed", label: "Failed", icon: XCircle, tone: "danger" },
  paused: { key: "paused", label: "Paused", icon: LockKeyhole, tone: "warning" },
  cancelled: { key: "cancelled", label: "Cancelled", icon: Ban, tone: "danger" },
};

const ARTIFACT_KIND_VISUALS: Partial<Record<ExecutionArtifact["kind"], RuntimeVisualDescriptor>> = {
  text: { key: "text", label: "Text artifact", icon: FileText, tone: "neutral" },
  json: { key: "json", label: "JSON artifact", icon: Braces, tone: "info" },
  code: { key: "code", label: "Code artifact", icon: FileCode2, tone: "info" },
  image: { key: "image", label: "Image artifact", icon: Image, tone: "neutral" },
  pdf: { key: "pdf", label: "PDF artifact", icon: FileText, tone: "neutral" },
  docx: { key: "docx", label: "Document artifact", icon: FileText, tone: "neutral" },
  spreadsheet: { key: "spreadsheet", label: "Spreadsheet artifact", icon: Database, tone: "neutral" },
  html: { key: "html", label: "HTML artifact", icon: Code2, tone: "info" },
  yaml: { key: "yaml", label: "YAML artifact", icon: Braces, tone: "info" },
  xml: { key: "xml", label: "XML artifact", icon: Braces, tone: "info" },
  csv: { key: "csv", label: "CSV artifact", icon: Database, tone: "neutral" },
  tsv: { key: "tsv", label: "TSV artifact", icon: Database, tone: "neutral" },
  url: { key: "url", label: "URL artifact", icon: Globe2, tone: "info" },
  file: { key: "file", label: "File artifact", icon: FileArchive, tone: "neutral" },
};

const METADATA_VISUALS: Record<string, RuntimeVisualDescriptor> = {
  cost: { key: "cost", label: "Cost", icon: CircleDollarSign, tone: "neutral" },
  duration: { key: "duration", label: "Duration", icon: Clock3, tone: "neutral" },
  attempts: { key: "attempts", label: "Attempts", icon: RotateCcw, tone: "retry" },
  tools: { key: "tools", label: "Tools", icon: Wrench, tone: "info" },
  warnings: { key: "warnings", label: "Warnings", icon: AlertTriangle, tone: "warning" },
  created_at: { key: "created_at", label: "Created", icon: CalendarClock, tone: "neutral" },
  started_at: { key: "started_at", label: "Started", icon: Activity, tone: "info" },
  completed_at: { key: "completed_at", label: "Completed", icon: CheckCircle2, tone: "success" },
  trace_source: { key: "trace_source", label: "Trace source", icon: Split, tone: "info" },
  response_source: { key: "response_source", label: "Response source", icon: FileOutput, tone: "success" },
  tools_source: { key: "tools_source", label: "Tools source", icon: ListChecks, tone: "info" },
  stop_reason: { key: "stop_reason", label: "Stop reason", icon: Ban, tone: "neutral" },
  model: { key: "model", label: "Model", icon: BrainCircuit, tone: "info" },
  session: { key: "session", label: "Session", icon: Bot, tone: "neutral" },
  workspace: { key: "workspace", label: "Workspace", icon: HardDrive, tone: "neutral" },
  actor: { key: "actor", label: "User and chat", icon: Bot, tone: "neutral" },
  status: { key: "status", label: "Status", icon: Activity, tone: "neutral" },
  task: { key: "task", label: "Task", icon: ListChecks, tone: "neutral" },
};

function normalizeToken(value: string | null | undefined): string {
  return String(value ?? "").trim().toLowerCase();
}

function containsAny(value: string, tokens: string[]) {
  return tokens.some((token) => value.includes(token));
}

function successAdjustedTone(success: boolean | null | undefined, fallback: SemanticTone): SemanticTone {
  if (success === false) return "danger";
  if (success === true && fallback === "danger") return "success";
  return fallback;
}

export function getRunGraphNodeVisual(type: RunGraphNodeType): RuntimeVisualDescriptor {
  return RUN_GRAPH_NODE_VISUALS[type];
}

export function getExecutionStatusVisual(status: ExecutionSummary["status"]): RuntimeVisualDescriptor {
  return EXECUTION_STATUS_VISUALS[status] ?? {
    key: "unknown_status",
    label: "Execution status",
    icon: Activity,
    tone: "neutral",
  };
}

export function getExecutionMetadataVisual(key: string): RuntimeVisualDescriptor {
  return METADATA_VISUALS[key] ?? {
    key: "metadata",
    label: "Metadata",
    icon: Braces,
    tone: "neutral",
  };
}

export function getTimelineVisual(item: Pick<ExecutionTimelineItem, "type" | "status">): RuntimeVisualDescriptor {
  const normalizedType = normalizeToken(item.type).replace(/[.\-]/g, "_");
  const nodeVisual = RUN_GRAPH_NODE_VISUALS[normalizedType as RunGraphNodeType];
  if (nodeVisual) {
    return {
      ...nodeVisual,
      tone: item.status === "error" ? "danger" : item.status === "warning" ? "warning" : nodeVisual.tone,
    };
  }
  if (containsAny(normalizedType, ["tool"])) return { key: "tool", label: "Tool event", icon: Wrench, tone: "info" };
  if (containsAny(normalizedType, ["policy", "approval"])) {
    return { key: "policy", label: "Policy event", icon: ShieldCheck, tone: "warning" };
  }
  if (containsAny(normalizedType, ["artifact", "file"])) {
    return { key: "artifact", label: "Artifact event", icon: FileArchive, tone: "neutral" };
  }
  if (containsAny(normalizedType, ["model", "provider", "llm"])) {
    return { key: "model", label: "Model event", icon: BrainCircuit, tone: "info" };
  }
  if (containsAny(normalizedType, ["error", "fail", "dlq"])) {
    return { key: "failure", label: "Failure event", icon: AlertTriangle, tone: "danger" };
  }
  const fallbackTone: SemanticTone =
    item.status === "error"
      ? "danger"
      : item.status === "warning"
        ? "warning"
        : item.status === "success"
          ? "success"
          : "info";
  return { key: "runtime_event", label: "Runtime event", icon: Activity, tone: fallbackTone };
}

export function getArtifactVisual(kind: ExecutionArtifact["kind"]): RuntimeVisualDescriptor {
  return ARTIFACT_KIND_VISUALS[kind] ?? {
    key: "artifact",
    label: "Artifact",
    icon: FileArchive,
    tone: "neutral",
  };
}

export function getToolVisual(input: ToolVisualInput): RuntimeVisualDescriptor {
  const tool = normalizeToken(input.tool);
  const category = normalizeToken(input.category);
  const haystack = `${tool} ${category}`;
  const metadataCategory = normalizeToken(
    typeof input.metadata?.category === "string" ? input.metadata.category : null,
  );
  const full = `${haystack} ${metadataCategory}`;

  if (tool === "task" || containsAny(full, ["child_run", "delegate", "subagent"])) {
    return { key: "delegate_task", label: "Delegate Task", icon: GitBranch, tone: successAdjustedTone(input.success, "info") };
  }
  if (containsAny(full, ["web_search", "fetch_url", "http", "research", "url"])) {
    const icon = containsAny(full, ["search"]) ? Search : Globe2;
    return { key: "network_research", label: "Web or HTTP", icon, tone: successAdjustedTone(input.success, "info") };
  }
  if (containsAny(full, ["browser"])) {
    return { key: "browser", label: "Browser action", icon: MousePointerClick, tone: successAdjustedTone(input.success, "info") };
  }
  if (containsAny(full, ["mcp", "connector", "integration"])) {
    return { key: "mcp", label: "MCP or integration", icon: PlugZap, tone: successAdjustedTone(input.success, "warning") };
  }
  if (containsAny(full, ["file_delete", "delete", "trash"])) {
    return { key: "file_delete", label: "File delete", icon: Trash2, tone: successAdjustedTone(input.success, "danger") };
  }
  if (containsAny(full, ["file_write", "file_move", "write", "move", "rename"])) {
    return { key: "file_write", label: "File write", icon: FilePenLine, tone: successAdjustedTone(input.success, "warning") };
  }
  if (containsAny(full, ["file", "read", "grep", "list"])) {
    return { key: "file_read", label: "File read", icon: FileSearch, tone: successAdjustedTone(input.success, "neutral") };
  }
  if (containsAny(full, ["shell", "command", "terminal", "exec"])) {
    return { key: "shell", label: "Shell command", icon: SquareTerminal, tone: successAdjustedTone(input.success, "warning") };
  }
  if (containsAny(full, ["sql", "database", "postgres", "db"])) {
    return { key: "database", label: "Database", icon: Database, tone: successAdjustedTone(input.success, "info") };
  }
  if (containsAny(full, ["git"])) {
    return { key: "git", label: "Git", icon: GitBranch, tone: successAdjustedTone(input.success, "neutral") };
  }
  if (containsAny(full, ["docker", "package", "plugin", "skill", "npm", "pip"])) {
    return { key: "package", label: "Package or plugin", icon: PackageCheck, tone: successAdjustedTone(input.success, "warning") };
  }
  if (containsAny(full, ["scheduler", "job", "routine"])) {
    return { key: "scheduler", label: "Scheduled job", icon: CalendarClock, tone: successAdjustedTone(input.success, "neutral") };
  }
  if (containsAny(full, ["agent", "runtime", "cache"])) {
    return { key: "runtime", label: "Runtime", icon: HardDrive, tone: successAdjustedTone(input.success, "neutral") };
  }
  if (containsAny(full, ["image", "vision"])) {
    return { key: "image", label: "Image", icon: Image, tone: successAdjustedTone(input.success, "info") };
  }
  if (containsAny(full, ["eval", "test", "quality"])) {
    return { key: "eval", label: "Evaluation", icon: FlaskConical, tone: successAdjustedTone(input.success, "info") };
  }
  if (containsAny(full, ["script", "code"])) {
    return { key: "script", label: "Script", icon: Code2, tone: successAdjustedTone(input.success, "warning") };
  }
  return { key: "tool", label: "Tool", icon: Wrench, tone: successAdjustedTone(input.success, "neutral") };
}
