import type { LucideIcon, LucideProps } from "lucide-react";
import {
  Activity,
  BookOpen,
  CalendarPlus,
  Coins,
  FolderSearch,
  Hammer,
  History,
  Home,
  Inbox,
  ListChecks,
  Network,
  Play,
  ShieldQuestion,
  Sparkles,
  Terminal,
  Waypoints,
} from "lucide-react";
import type { AgentDisplay } from "@/lib/agent-constants";
import type { AgentStats, Task } from "@/lib/types";
import type { PendingApproval } from "@/lib/contracts/sessions";

export interface SkillEntry {
  id: string;
  title: string;
  description?: string;
  category?: string;
}

export interface ToolEntry {
  id: string;
  title: string;
  description?: string;
  category?: string;
}

export type CommandCategory =
  | "agents"
  | "pages"
  | "actions"
  | "recents"
  | "skills"
  | "tools"
  | "approvals";

export interface Command {
  id: string;
  category: CommandCategory;
  label: string;
  description?: string;
  keywords?: string[];
  icon: LucideIcon | ((props: LucideProps) => React.ReactElement);
  onExecute: () => void;
}

export interface CommandBarContext {
  agents: AgentDisplay[];
  stats: AgentStats[] | undefined;
  skills?: SkillEntry[];
  tools?: ToolEntry[];
  pendingApprovals?: PendingApproval[];
  router: { push: (href: string) => void };
  t: (key: string, params?: Record<string, unknown>) => string;
  openAgentDetail: (agentId: string) => void;
  openSession?: (agentId: string, sessionId: string) => void;
}

export interface CommandGroup {
  category: CommandCategory;
  heading: string;
  commands: Command[];
}

function normalize(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim();
}

export function scoreCommand(command: Command, query: string): number {
  if (!query) return 1;

  const q = normalize(query);
  const label = normalize(command.label);
  const desc = command.description ? normalize(command.description) : "";
  const keywords = (command.keywords ?? []).map(normalize);

  if (label === q) return 1000;
  if (label.startsWith(q)) return 800;
  if (keywords.some((k) => k === q)) return 700;
  if (label.includes(q)) return 600;
  if (keywords.some((k) => k.startsWith(q))) return 500;
  if (keywords.some((k) => k.includes(q))) return 400;
  if (desc.includes(q)) return 300;
  if (isSubsequence(q, label)) return 200;
  if (keywords.some((k) => isSubsequence(q, k))) return 100;
  return 0;
}

function isSubsequence(needle: string, haystack: string): boolean {
  let i = 0;
  for (const ch of haystack) {
    if (ch === needle[i]) i += 1;
    if (i === needle.length) return true;
  }
  return false;
}

export function rankCommands(commands: Command[], query: string): Command[] {
  if (!query.trim()) return commands;
  return commands
    .map((command) => ({ command, score: scoreCommand(command, query) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.command);
}

export function groupCommands(
  commands: Command[],
  t: CommandBarContext["t"],
): CommandGroup[] {
  const order: CommandCategory[] = [
    "approvals",
    "agents",
    "pages",
    "actions",
    "skills",
    "tools",
    "recents",
  ];
  const headings: Record<CommandCategory, string> = {
    approvals: t("commandBar.groups.approvals", { defaultValue: "Aprovações" }),
    agents: t("commandBar.groups.agents"),
    pages: t("commandBar.groups.pages"),
    actions: t("commandBar.groups.actions"),
    skills: t("commandBar.groups.skills", { defaultValue: "Skills" }),
    tools: t("commandBar.groups.tools", { defaultValue: "Tools" }),
    recents: t("commandBar.groups.recents"),
  };

  const groups = new Map<CommandCategory, Command[]>();
  for (const command of commands) {
    const bucket = groups.get(command.category) ?? [];
    bucket.push(command);
    groups.set(command.category, bucket);
  }

  return order
    .filter((category) => (groups.get(category) ?? []).length > 0)
    .map((category) => ({
      category,
      heading: headings[category],
      commands: groups.get(category) ?? [],
    }));
}

export function buildCommands(ctx: CommandBarContext): Command[] {
  return [
    ...buildApprovalCommands(ctx),
    ...buildAgentCommands(ctx),
    ...buildPageCommands(ctx),
    ...buildActionCommands(ctx),
    ...buildSkillCommands(ctx),
    ...buildToolCommands(ctx),
    ...buildRecentCommands(ctx),
  ];
}

function buildApprovalCommands(ctx: CommandBarContext): Command[] {
  if (!ctx.pendingApprovals?.length) return [];
  return ctx.pendingApprovals.slice(0, 10).map((approval) => ({
    id: `approval:${approval.approval_id}`,
    category: "approvals" as const,
    label: approval.description || approval.approval_id,
    description: "Pending approval",
    keywords: [
      "approval",
      "aprovacao",
      "pending",
      approval.agent_id ?? "",
      approval.session_id ?? "",
    ].filter(Boolean),
    icon: ShieldQuestion,
    onExecute: () => {
      if (approval.session_id && approval.agent_id && ctx.openSession) {
        ctx.openSession(approval.agent_id, approval.session_id);
      } else if (approval.session_id) {
        ctx.router.push(
          `/sessions?session=${encodeURIComponent(approval.session_id)}`,
        );
      }
    },
  }));
}

function buildSkillCommands(ctx: CommandBarContext): Command[] {
  if (!ctx.skills?.length) return [];
  return ctx.skills.map((skill) => ({
    id: `skill:${skill.id}`,
    category: "skills" as const,
    label: skill.title || skill.id,
    description: skill.description || undefined,
    keywords: [skill.id, "skill", "expert"],
    icon: BookOpen,
    onExecute: () =>
      ctx.router.push(
        `/sessions?skill=${encodeURIComponent(skill.id)}`,
      ),
  }));
}

function buildToolCommands(ctx: CommandBarContext): Command[] {
  if (!ctx.tools?.length) return [];
  return ctx.tools.map((tool) => ({
    id: `tool:${tool.id}`,
    category: "tools" as const,
    label: tool.title || tool.id,
    description: tool.description || undefined,
    keywords: [tool.id, "tool", "agent_cmd"],
    icon: Hammer,
    onExecute: () =>
      ctx.router.push(
        `/sessions?tool=${encodeURIComponent(tool.id)}`,
      ),
  }));
}

function makeAgentDotIcon(color: string) {
  return function AgentDotIcon({ className }: LucideProps) {
    return (
      <span
        className={className}
        aria-hidden="true"
        style={{
          display: "inline-flex",
          width: "0.625rem",
          height: "0.625rem",
          borderRadius: "9999px",
          backgroundColor: color,
          flexShrink: 0,
        }}
      />
    );
  };
}

function buildAgentCommands(ctx: CommandBarContext): Command[] {
  return ctx.agents.map((agent) => ({
    id: `agent:${agent.id}`,
    category: "agents" as const,
    label: agent.label,
    description: ctx.t("commandBar.agent.description"),
    keywords: [agent.id, "agent", "agent", "agente"],
    icon: makeAgentDotIcon(agent.color),
    onExecute: () => ctx.openAgentDetail(agent.id),
  }));
}

function buildPageCommands(ctx: CommandBarContext): Command[] {
  const entries: Array<{
    id: string;
    path: string;
    labelKey: string;
    icon: LucideIcon;
    keywords: string[];
  }> = [
    { id: "home", path: "/", labelKey: "commandBar.pages.home", icon: Home, keywords: ["home", "overview", "inicio"] },
    { id: "control-plane", path: "/control-plane", labelKey: "commandBar.pages.controlPlane", icon: Sparkles, keywords: ["agents", "agentes", "control", "plane", "catalog"] },
    { id: "memory", path: "/memory", labelKey: "commandBar.pages.memory", icon: Network, keywords: ["memory", "memorias", "memoria", "graph", "curation"] },
    { id: "schedules", path: "/schedules", labelKey: "commandBar.pages.schedules", icon: CalendarPlus, keywords: ["schedules", "schedule", "routines", "rotinas", "cron"] },
    { id: "sessions", path: "/sessions", labelKey: "commandBar.pages.sessions", icon: Terminal, keywords: ["sessions", "sessoes", "sessao", "chat"] },
    { id: "tasks", path: "/tasks", labelKey: "commandBar.pages.tasks", icon: ListChecks, keywords: ["tasks", "tarefas"] },
    { id: "runtime", path: "/runtime", labelKey: "commandBar.pages.runtime", icon: Activity, keywords: ["runtime", "execution", "live"] },
    { id: "executions", path: "/executions", labelKey: "commandBar.pages.executions", icon: History, keywords: ["executions", "history", "historico", "execucoes"] },
    { id: "costs", path: "/costs", labelKey: "commandBar.pages.costs", icon: Coins, keywords: ["costs", "custos", "billing"] },
    { id: "dlq", path: "/dlq", labelKey: "commandBar.pages.dlq", icon: Inbox, keywords: ["dlq", "dead letter", "retry"] },
  ];

  return entries.map((entry) => ({
    id: `page:${entry.id}`,
    category: "pages" as const,
    label: ctx.t(entry.labelKey),
    keywords: entry.keywords,
    icon: entry.icon,
    onExecute: () => ctx.router.push(entry.path),
  }));
}

function buildActionCommands(ctx: CommandBarContext): Command[] {
  return [
    {
      id: "action:run-task",
      category: "actions",
      label: ctx.t("overview.composer.actions.runTask"),
      keywords: ["run", "task", "executar", "rodar"],
      icon: Play,
      onExecute: () => ctx.router.push("/runtime"),
    },
    {
      id: "action:new-schedule",
      category: "actions",
      label: ctx.t("overview.composer.actions.newSchedule"),
      keywords: ["new", "schedule", "cron", "routine", "novo", "agendar"],
      icon: CalendarPlus,
      onExecute: () => ctx.router.push("/schedules"),
    },
    {
      id: "action:new-agent",
      category: "actions",
      label: ctx.t("overview.composer.actions.newAgent"),
      keywords: ["new", "agent", "agent", "create", "novo", "agente", "criar"],
      icon: Sparkles,
      onExecute: () => ctx.router.push("/control-plane"),
    },
    {
      id: "action:review-memory",
      category: "actions",
      label: ctx.t("overview.composer.actions.reviewMemory"),
      keywords: ["memory", "review", "memoria", "curation", "curadoria"],
      icon: FolderSearch,
      onExecute: () => ctx.router.push("/memory"),
    },
  ];
}

const RECENT_LIMIT = 5;

function buildRecentCommands(ctx: CommandBarContext): Command[] {
  if (!ctx.stats) return [];

  const entries: Array<{ task: Task; agentId: string }> = [];
  for (const stats of ctx.stats) {
    for (const task of stats.recentTasks ?? []) {
      entries.push({ task, agentId: stats.agentId });
    }
  }

  entries.sort((a, b) => {
    const aTime = new Date(a.task.created_at ?? 0).getTime();
    const bTime = new Date(b.task.created_at ?? 0).getTime();
    return bTime - aTime;
  });

  return entries.slice(0, RECENT_LIMIT).map(({ task, agentId }) => {
    const agentLabel = ctx.agents.find((b) => b.id === agentId)?.label ?? agentId;
    const query = task.query_text?.trim() ?? "";
    const label = query.length > 0 ? query : ctx.t("commandBar.recents.noQuery");
    return {
      id: `recent:${task.id}`,
      category: "recents" as const,
      label,
      description: agentLabel,
      keywords: [agentId, agentLabel, String(task.id)],
      icon: Waypoints,
      onExecute: () => ctx.router.push(`/runtime?agent=${encodeURIComponent(agentId)}`),
    };
  });
}
